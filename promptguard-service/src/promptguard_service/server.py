import os
from functools import lru_cache

import torch
from fastapi import FastAPI
from shared_models import configure_logging
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# Setup logging
logger = configure_logging(__name__)

app = FastAPI(title="PromptGuard Service")


@lru_cache(maxsize=1)
def load_model():
    """Load model once at startup."""
    model_id = os.getenv("PROMPTGUARD_MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-86M")
    hf_token = os.getenv("HF_TOKEN")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    logger.info("Loading PromptGuard model", model_id=model_id, device=device)
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id, token=hf_token
    )
    model.to(device).eval()
    logger.info("Model loaded successfully")

    return model, tokenizer


@app.get("/health")
def health():
    """Health check."""
    load_model()
    return {"status": "OK"}


@app.get("/v1/models")
def models():
    """OpenAI models list (for llama-stack init)."""
    model_id = os.getenv("PROMPTGUARD_MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-86M")
    return {"object": "list", "data": [{"id": model_id, "object": "model"}]}


@app.post("/v1/chat/completions")
def chat_completions(request: dict):
    """Llama Guard protocol endpoint.

    Receives: {"messages": [{"role": "user", "content": "..."}]}
    Returns: {"choices": [{"message": {"content": "safe" or "unsafe\nS9"}}]}
    """
    model, tokenizer = load_model()
    device = next(model.parameters()).device

    # Extract user message
    messages = request.get("messages", [])
    user_msg = next(
        (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
    )

    # Extract from Llama Guard template if present
    original_length = len(user_msg)
    if "<BEGIN CONVERSATION>" in user_msg:
        start = user_msg.find("<BEGIN CONVERSATION>") + len("<BEGIN CONVERSATION>")
        end = user_msg.find("<END CONVERSATION>")
        # Use len(user_msg) if marker not found to avoid excluding last character
        if end == -1:
            end = len(user_msg)
        conversation = user_msg[start:end].strip()

        # Get last "User:" message
        if "User:" in conversation:
            user_msg = conversation.split("User:")[-1].strip()
            # Remove assistant response if present
            if "\nAssistant:" in user_msg:
                user_msg = user_msg.split("\nAssistant:")[0].strip()

    # Run inference
    inputs = tokenizer(
        user_msg, return_tensors="pt", truncation=True, max_length=512
    ).to(device)

    with torch.no_grad():
        logits = model(**inputs).logits
        probabilities = torch.softmax(logits, dim=-1)
        prediction = torch.argmax(probabilities, dim=-1).item()
        confidence = probabilities[0][prediction].item()

    # Return Llama Guard format
    result = "unsafe\nS9" if prediction == 1 else "safe"

    # Log the classification
    logger.info(
        "Classification result",
        result=result,
        confidence=round(confidence, 4),
        message_length=len(user_msg),
        original_length=original_length,
    )

    return {
        "id": "chatcmpl-pg",
        "object": "chat.completion",
        "model": os.getenv(
            "PROMPTGUARD_MODEL_ID", "meta-llama/Llama-Prompt-Guard-2-86M"
        ),
        "choices": [{"message": {"role": "assistant", "content": result}}],
        "usage": {
            "prompt_tokens": len(user_msg.split()),
            "completion_tokens": len(result.split()),
            "total_tokens": len(user_msg.split()) + len(result.split()),
        },
    }


@app.on_event("startup")
def startup():
    """Preload model at startup."""
    load_model()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
