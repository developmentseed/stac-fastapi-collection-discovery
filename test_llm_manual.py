"""Manual test script for LLM client. Delete after testing."""

import asyncio

from stac_fastapi.collection_discovery.llm import LLMClient
from stac_fastapi.collection_discovery.settings import Settings


async def main():
    settings = Settings()
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")

    client = LLMClient.from_settings(settings)

    response = await client.generate(
        prompt="List 3 scientific terms relating to 'deforestation' as a JSON array of strings",
        system="Respond with valid JSON only, no additional text.",
        json_mode=True,
    )

    print(f"\nContent: {response.content}")
    print(f"Tokens: {response.input_tokens} in, {response.output_tokens} out")
    print(f"Latency: {response.latency_ms:.0f}ms")
    print(f"Parsed: {response.parse_json()}")


if __name__ == "__main__":
    asyncio.run(main())
