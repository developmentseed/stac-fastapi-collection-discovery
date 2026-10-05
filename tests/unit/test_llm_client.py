import sys
import types
from unittest.mock import AsyncMock, patch

import pytest

from stac_fastapi.collection_discovery.llm.client import (
    LLMClient,
    LLMRateLimitError,
)
from stac_fastapi.collection_discovery.settings import Settings


class FakeSDKClient:
    """Records constructor kwargs; the real SDKs are optional extras."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def fake_sdks(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=FakeSDKClient)
    )
    monkeypatch.setitem(
        sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=FakeSDKClient)
    )


def test_settings_default_timeout_and_validation():
    assert Settings().llm_timeout == 30.0
    with pytest.raises(ValueError):
        Settings(llm_timeout=0)


@pytest.mark.parametrize(
    "provider, prefix", [("openai", "gpt-"), ("anthropic", "claude-")]
)
def test_settings_default_model_matches_provider(provider, prefix):
    assert Settings(llm_provider=provider).llm_model.startswith(prefix)


def test_settings_explicit_model_is_kept():
    settings = Settings(llm_provider="anthropic", llm_model="my-model")
    assert settings.llm_model == "my-model"


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_from_settings_passes_timeout_to_sdk_client(fake_sdks, provider):
    client = LLMClient.from_settings(
        Settings(llm_provider=provider, llm_api_key="k", llm_timeout=7.5)
    )
    sdk_client = client._openai_client or client._anthropic_client
    assert client._timeout == 7.5
    assert sdk_client.kwargs["timeout"] == 7.5
    assert sdk_client.kwargs["max_retries"] == 1


def test_timeout_defaults_to_30(fake_sdks):
    client = LLMClient(provider="openai", api_key="k", model="m")
    assert client._timeout == 30.0
    assert client._openai_client.kwargs["timeout"] == 30.0


async def test_rate_limit_sleep_is_capped(fake_sdks):
    client = LLMClient(provider="openai", api_key="k", model="m", max_retries=1)
    resp = types.SimpleNamespace(input_tokens=0, output_tokens=0, total_tokens=0)
    with (
        patch.object(
            client,
            "_generate_openai",
            AsyncMock(side_effect=[LLMRateLimitError("x", retry_after=3600), resp]),
        ),
        patch("asyncio.sleep", AsyncMock()) as sleep,
    ):
        await client.generate("p")
    sleep.assert_awaited_once_with(30.0)
