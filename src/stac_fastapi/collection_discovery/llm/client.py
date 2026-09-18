"""LLM client abstraction supporting multiple providers."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from stac_fastapi.collection_discovery.settings import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMConfigurationError(LLMError):
    """Raised when LLM is not properly configured."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limited by the LLM provider."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class LLMResponse:
    """Response from an LLM generation request."""

    content: str
    """The generated text content."""

    input_tokens: int
    """Number of input tokens used."""

    output_tokens: int
    """Number of output tokens generated."""

    latency_ms: float
    """Request latency in milliseconds."""

    model: str
    """Model that generated the response."""

    provider: str
    """Provider that served the request (openai or anthropic)."""

    raw_response: dict[str, Any] = field(default_factory=dict)
    """Raw response from the provider for debugging."""

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens

    def parse_json(self) -> dict[str, Any] | list[Any] | None:
        """Parse the content as JSON, returning None if invalid."""
        try:
            return json.loads(self.content)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            content = self.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                # Remove first line (```json) and last line (```)
                if len(lines) >= 3:
                    json_content = "\n".join(lines[1:-1])
                    try:
                        return json.loads(json_content)
                    except json.JSONDecodeError:
                        pass
            return None


class LLMClient:
    """Unified LLM client supporting OpenAI and Anthropic providers.

    This client provides a common interface for LLM operations, handling:
    - Provider-specific API differences
    - Rate limiting with exponential backoff
    - Token usage logging for cost tracking
    - Graceful error handling

    Example:
        ```python
        client = LLMClient.from_settings(settings)
        response = await client.generate(
            prompt="What are synonyms for 'coral bleaching'?",
            system="You are a helpful assistant.",
        )
        print(response.content)
        ```
    """

    def __init__(
        self,
        provider: Literal["openai", "anthropic"],
        api_key: str,
        model: str,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
    ):
        """Initialize the LLM client.

        Args:
            provider: The LLM provider ("openai" or "anthropic")
            api_key: API key for the provider
            model: Model name to use
            max_retries: Maximum number of retries on rate limit errors
            base_retry_delay: Base delay in seconds for exponential backoff
        """
        self.provider = provider
        self.model = model
        self._max_retries = max_retries
        self._base_retry_delay = base_retry_delay

        # Lazy-load provider clients to avoid import errors when deps not installed
        self._openai_client: Any = None
        self._anthropic_client: Any = None

        if provider == "openai":
            self._init_openai(api_key)
        elif provider == "anthropic":
            self._init_anthropic(api_key)
        else:
            raise LLMConfigurationError(f"Unsupported provider: {provider}")

    def _init_openai(self, api_key: str) -> None:
        """Initialize OpenAI client."""
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise LLMConfigurationError(
                "OpenAI package not installed. Install with: uv sync --extra llm"
            ) from e

        self._openai_client = AsyncOpenAI(api_key=api_key)

    def _init_anthropic(self, api_key: str) -> None:
        """Initialize Anthropic client."""
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise LLMConfigurationError(
                "Anthropic package not installed. Install with: uv sync --extra llm"
            ) from e

        self._anthropic_client = AsyncAnthropic(api_key=api_key)

    @classmethod
    def from_settings(cls, settings: "Settings") -> "LLMClient":
        """Create an LLMClient from application settings.

        Args:
            settings: Application settings containing LLM configuration

        Returns:
            Configured LLMClient instance

        Raises:
            LLMConfigurationError: If LLM is not configured or misconfigured
        """
        if not settings.llm_provider:
            raise LLMConfigurationError(
                "LLM provider not configured. Set LLM_PROVIDER environment variable."
            )

        if not settings.llm_api_key:
            raise LLMConfigurationError(
                "LLM API key not configured. Set LLM_API_KEY environment variable."
            )

        return cls(
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Generate text from the LLM.

        Args:
            prompt: The user prompt/query
            system: Optional system prompt for context
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate
            json_mode: If True, request JSON output format

        Returns:
            LLMResponse with generated content and metadata

        Raises:
            LLMError: On generation failure after retries
            LLMRateLimitError: If rate limited and retries exhausted
        """
        start_time = time.perf_counter()

        for attempt in range(self._max_retries + 1):
            try:
                if self.provider == "openai":
                    response = await self._generate_openai(
                        prompt, system, temperature, max_tokens, json_mode
                    )
                else:
                    response = await self._generate_anthropic(
                        prompt, system, temperature, max_tokens, json_mode
                    )

                latency_ms = (time.perf_counter() - start_time) * 1000
                response.latency_ms = latency_ms

                # Log token usage for cost tracking
                logger.info(
                    "LLM request completed",
                    extra={
                        "provider": self.provider,
                        "model": self.model,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                        "total_tokens": response.total_tokens,
                        "latency_ms": round(latency_ms, 2),
                    },
                )

                return response

            except LLMRateLimitError as e:
                if attempt == self._max_retries:
                    raise

                delay = e.retry_after or (self._base_retry_delay * (2**attempt))
                logger.warning(
                    f"Rate limited by {self.provider}, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{self._max_retries})"
                )
                await asyncio.sleep(delay)

        # Should not reach here, but satisfy type checker
        raise LLMError("Max retries exceeded")

    async def _generate_openai(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Generate using OpenAI API."""
        from openai import RateLimitError

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = await self._openai_client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            retry_after = None
            if hasattr(e, "response") and e.response:
                retry_after_header = e.response.headers.get("retry-after")
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        pass
            raise LLMRateLimitError(str(e), retry_after=retry_after) from e
        except Exception as e:
            raise LLMError(f"OpenAI API error: {e}") from e

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=0,  # Will be set by caller
            model=response.model,
            provider="openai",
            raw_response=response.model_dump(),
        )

    async def _generate_anthropic(
        self,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> LLMResponse:
        """Generate using Anthropic API."""
        from anthropic import RateLimitError

        messages = [{"role": "user", "content": prompt}]

        # For JSON mode, add instruction to system prompt
        effective_system = system or ""
        if json_mode:
            json_instruction = "Respond with valid JSON only, no additional text."
            effective_system = (
                f"{effective_system}\n\n{json_instruction}"
                if effective_system
                else json_instruction
            )

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if effective_system:
            kwargs["system"] = effective_system

        try:
            response = await self._anthropic_client.messages.create(**kwargs)
        except RateLimitError as e:
            retry_after = None
            if hasattr(e, "response") and e.response:
                retry_after_header = e.response.headers.get("retry-after")
                if retry_after_header:
                    try:
                        retry_after = float(retry_after_header)
                    except ValueError:
                        pass
            raise LLMRateLimitError(str(e), retry_after=retry_after) from e
        except Exception as e:
            raise LLMError(f"Anthropic API error: {e}") from e

        # Extract text from content blocks
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=0,  # Will be set by caller
            model=response.model,
            provider="anthropic",
            raw_response=response.model_dump(),
        )

    @property
    def is_configured(self) -> bool:
        """Check if the client is properly configured."""
        return (self._openai_client is not None) or (self._anthropic_client is not None)


def get_llm_client(settings: "Settings") -> LLMClient | None:
    """Get an LLM client if configured, otherwise return None.

    This is a convenience function for optional LLM usage - it returns None
    instead of raising an error when LLM is not configured.

    Args:
        settings: Application settings

    Returns:
        LLMClient if configured, None otherwise
    """
    if not settings.llm_provider or not settings.llm_api_key:
        return None

    try:
        return LLMClient.from_settings(settings)
    except LLMConfigurationError:
        return None
