"""Manual test script for date parser. Delete after testing."""

import asyncio
from datetime import date

from stac_fastapi.collection_discovery.llm import LLMClient, DateParser
from stac_fastapi.collection_discovery.settings import Settings


async def main():
    settings = Settings()
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")

    client = LLMClient.from_settings(settings)
    parser = DateParser(client)

    # Test cases
    test_expressions = [
        "summer 2020",
        "last year",
        "March to June 2023",
        "past 6 months",
        "2020",
        "winter 2021",
    ]

    # Use a fixed reference date for reproducible results
    reference = date(2026, 9, 8)

    for expr in test_expressions:
        print(f"\n--- Parsing: '{expr}' ---")
        result = await parser.parse(expr, reference_date=reference)

        if result.success:
            print(f"  Range: {result.datetime_range}")
            print(f"  Start: {result.start_date}, End: {result.end_date}")
        else:
            print(f"  Error: {result.error}")

        print(f"  Time: {result.parse_time_ms:.0f}ms")


if __name__ == "__main__":
    asyncio.run(main())
