import os
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import List

import torch
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from shared_models import configure_logging
from tracing_config.auto_tracing import run as auto_tracing_run
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from . import __version__

# Configure logging and tracing
SERVICE_NAME = "promptguard-service"
logger = configure_logging(SERVICE_NAME)
auto_tracing_run(SERVICE_NAME, logger)

MODEL_ID = os.getenv("PROMPTGUARD_MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-86M")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    messages: List[ChatMessage]


def _parse_llama_guard_template(content: str) -> str:
    """Extract user message from Llama Guard template."""
    if "<BEGIN CONVERSATION>" not in content:
        return content

    start = content.find("<BEGIN CONVERSATION>") + len("<BEGIN CONVERSATION>")
    end = content.find("<END CONVERSATION>")
    if end == -1:
        end = len(content)
    conversation = content[start:end].strip()

    if "User:" in conversation:
        user_msg = conversation.split("User:")[-1].strip()
        if "\nAssistant:" in user_msg:
            user_msg = user_msg.split("\nAssistant:")[0].strip()
        return user_msg

    return conversation


@lru_cache(maxsize=1)
def load_model():
    """Load model once at startup."""
    hf_token = os.getenv("HF_TOKEN")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    logger.info("Loading PromptGuard model", model_id=MODEL_ID, device=str(device))
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, token=hf_token)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_ID, token=hf_token)
    model.to(device).eval()
    logger.info("Model loaded successfully")

    return model, tokenizer, device


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan for model preloading."""
    load_model()
    yield


app = FastAPI(
    title="Self-Service Agent PromptGuard Service",
    description="Prompt injection and jailbreak detection service",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """Health check."""
    try:
        load_model()
        return {"status": "OK", "service": SERVICE_NAME}
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable: model not loaded",
        )


@app.get("/v1/models")
async def models():
    """OpenAI models list (for llama-stack compatibility)."""
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    """Llama Guard protocol endpoint for prompt injection detection."""
    try:
        model, tokenizer, device = load_model()

        # Extract user message
        user_msg = next(
            (m.content for m in reversed(request.messages) if m.role == "user"), ""
        )
        if not user_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No user message found in request",
            )

        # Parse Llama Guard template if present
        user_msg = _parse_llama_guard_template(user_msg)
        if not user_msg.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Empty message after template parsing",
            )

        # Run inference
        inputs = tokenizer(
            user_msg, return_tensors="pt", truncation=True, max_length=512
        ).to(device)
        prompt_tokens = inputs["input_ids"].shape[1]

        with torch.no_grad():
            logits = model(**inputs).logits
            probabilities = torch.softmax(logits, dim=-1)
            prediction = torch.argmax(probabilities, dim=-1).item()
            confidence = probabilities[0][prediction].item()

        result = "unsafe\nS9" if prediction == 1 else "safe"
        completion_tokens = tokenizer(result, return_tensors="pt")["input_ids"].shape[1]

        logger.info(
            "Classification result",
            result=result,
            confidence=round(confidence, 4),
            message_length=len(user_msg),
        )

        return {
            "id": "chatcmpl-pg",
            "object": "chat.completion",
            "model": MODEL_ID,
            "choices": [{"message": {"role": "assistant", "content": result}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error processing request", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(
        "promptguard_service.server:app",
        host=host,
        port=port,
        reload=False,
    )
