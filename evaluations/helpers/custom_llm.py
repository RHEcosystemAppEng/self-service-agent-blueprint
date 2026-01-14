#!/usr/bin/env python3

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple, Type, Union, cast

import instructor
import openai
from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

from .token_counter import count_tokens_from_response

# Configure logging
logger = logging.getLogger(__name__)


class CustomLLM(DeepEvalBaseLLM):
    """Custom LLM class for using non-OpenAI endpoints with deepeval"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model_name: str | None = None,
        use_structured_output: bool = False,
    ):
        """
        Initialize the CustomLLM with API credentials and configuration.

        Args:
            api_key: API key for authentication
            base_url: Base URL for the LLM API endpoint
            model_name: Optional model name
            use_structured_output: Enable structured output with Pydantic schema validation and retries
        """
        self.api_key = api_key
        self.base_url = base_url
        self.use_structured_output = use_structured_output
        # Use LLM_ID environment variable if model_name not provided
        self.model_name = model_name or os.getenv("LLM_ID") or ""
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)

    def load_model(self) -> Any:
        """
        Load and return the OpenAI client instance.

        Returns:
            OpenAI client configured with custom endpoint and API key
        """
        return self.client

    def generate(  # type: ignore[override]
        self, prompt: str, schema: Optional[Type[BaseModel]] = None
    ) -> Union[str, BaseModel]:
        """
        Generate a response to the given prompt using the custom LLM.

        Args:
            prompt: The input prompt to generate a response for
            schema: Optional Pydantic BaseModel class for structured output (only when use_structured_output=True)

        Returns:
            Pydantic model instance if schema provided and use_structured_output=True, otherwise string response

        Raises:
            Exception: If the API call fails or returns an error
        """
        client = self.load_model()
        try:
            # If instructor is enabled and schema is provided, use instructor for structured output
            if self.use_structured_output and schema is not None:
                logger.debug(
                    f"Generating with schema using instructor: {schema.__name__}"
                )
                instructor_client = instructor.from_openai(client)

                # Use create_with_completion to get both the model and the raw completion for token counting
                resp, completion = (
                    instructor_client.chat.completions.create_with_completion(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_model=schema,
                        temperature=0.1,
                        max_tokens=4096,
                        max_retries=3,
                    )
                )

                # Count tokens from the raw completion
                count_tokens_from_response(
                    completion, self.model_name, "custom_llm_evaluation"
                )

                return cast(BaseModel, resp)

            # Regular mode (without instructor)
            api_kwargs: Dict[str, Any] = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            }

            # Try to enable JSON mode if the prompt appears to be asking for JSON or if schema is provided
            if schema is not None or any(
                keyword in prompt.lower() for keyword in ["json", "schema", "format"]
            ):
                try:
                    api_kwargs["response_format"] = {"type": "json_object"}
                    logger.debug("Enabled JSON mode for structured output")
                except Exception as e:
                    logger.debug(f"JSON mode not supported, continuing without it: {e}")

            response = client.chat.completions.create(**api_kwargs)

            count_tokens_from_response(
                response, self.model_name, "custom_llm_evaluation"
            )

            content = response.choices[0].message.content

            # If schema is provided, parse JSON and create Pydantic model
            if schema is not None and content:
                try:
                    data = json.loads(content)
                    return schema(**data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"Failed to parse response as {schema.__name__}: {e}")
                    logger.debug(f"Raw content: {content}")
                    raise

            return str(content) if content is not None else ""
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    async def a_generate(  # type: ignore[override]
        self, prompt: str, schema: Optional[Type[BaseModel]] = None
    ) -> Union[str, BaseModel]:
        """
        Asynchronously generate a response to the given prompt using the custom LLM.

        Args:
            prompt: The input prompt to generate a response for
            schema: Optional Pydantic BaseModel class for structured output (only when use_structured_output=True)

        Returns:
            Pydantic model instance if schema provided and use_structured_output=True, otherwise string response

        Raises:
            Exception: If the API call fails or returns an error
        """
        try:
            async_client = openai.AsyncOpenAI(
                api_key=self.api_key, base_url=self.base_url
            )

            # If instructor is enabled and schema is provided, use instructor for structured output
            if self.use_structured_output and schema is not None:
                logger.debug(
                    f"Async generating with schema using instructor: {schema.__name__}"
                )
                instructor_client = instructor.from_openai(async_client)

                # Use create_with_completion to get both the model and the raw completion for token counting
                resp, completion = (
                    await instructor_client.chat.completions.create_with_completion(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_model=schema,
                        temperature=0.1,
                        max_tokens=4096,
                        max_retries=3,
                    )
                )

                # Count tokens from the raw completion
                count_tokens_from_response(
                    completion, self.model_name, "custom_llm_evaluation_async"
                )

                return resp

            # Regular mode (without instructor)
            api_kwargs: Dict[str, Any] = {
                "model": self.model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 2048,
            }

            # Try to enable JSON mode if the prompt appears to be asking for JSON or if schema is provided
            if schema is not None or any(
                keyword in prompt.lower() for keyword in ["json", "schema", "format"]
            ):
                try:
                    api_kwargs["response_format"] = {"type": "json_object"}
                    logger.debug("Enabled JSON mode for structured output")
                except Exception as e:
                    logger.debug(f"JSON mode not supported, continuing without it: {e}")

            response = await async_client.chat.completions.create(**api_kwargs)

            count_tokens_from_response(
                response, self.model_name, "custom_llm_evaluation_async"
            )

            content = response.choices[0].message.content

            # If schema is provided, parse JSON and create Pydantic model
            if schema is not None and content:
                try:
                    data = json.loads(content)
                    return schema(**data)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"Failed to parse response as {schema.__name__}: {e}")
                    logger.debug(f"Raw content: {content}")
                    raise

            return str(content) if content is not None else ""

        except Exception as e:
            logger.error(f"Error generating async response: {e}")
            raise e

    def get_model_name(self) -> str:
        """
        Get a human-readable name for this model instance.

        Returns:
            Formatted model name string
        """
        return f"Custom {self.model_name}"


def get_api_configuration(
    api_endpoint: Optional[str] = None, api_key: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], str]:
    """
    Get API configuration from arguments or environment variables

    Args:
        api_endpoint: Custom API endpoint URL
        api_key: API key or token

    Returns:
        Tuple of (api_key, endpoint, model_name)
    """
    # Get API key from argument or environment
    final_api_key = api_key or os.getenv("LLM_API_TOKEN")
    if not final_api_key:
        logger.warning(
            "No API key found. Set LLM_API_TOKEN environment variable or pass --api-key"
        )

    # Get endpoint from argument or environment
    final_endpoint = api_endpoint or os.getenv("LLM_URL")

    # Get model name from environment
    model_name = os.getenv("LLM_ID", "")

    logger.debug(f"Using endpoint: {final_endpoint}")
    logger.debug(f"LLM Model ID: {model_name}")

    return final_api_key, final_endpoint, model_name
