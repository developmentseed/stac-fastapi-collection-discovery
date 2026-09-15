"""Manual test script for location parsing and geocoding. Delete after testing."""

import asyncio

from stac_fastapi.collection_discovery.llm import (
    Geocoder,
    LLMClient,
    LocationExtractor,
    LocationParser,
)
from stac_fastapi.collection_discovery.settings import Settings

# Locations that geocode well with Nominatim (specific cities, countries, landmarks)
GOOD_TEST_QUERIES = [
    "coral bleaching near Hawaii",
    "deforestation in Brazil",
    "air pollution in Los Angeles",
    "wildfires in California",
    "flooding in Houston, Texas",
    "sea surface temperature near Australia",
]

# Locations that DON'T geocode well (too vague, ambiguous, or regional)
# Kept here for documentation but not tested
BAD_TEST_QUERIES = [
    "wildfires in Northern California",  # Resolves to Cyprus
    "deforestation in the Amazon",  # Resolves to Amazon warehouse in Minnesota
    "data for the Arctic",  # Too broad
    "imagery of the Midwest",  # Regional name not well defined
]


async def main():
    settings = Settings()
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")

    client = LLMClient.from_settings(settings)
    geocoder = Geocoder()
    extractor = LocationExtractor(client)
    parser = LocationParser(client, geocoder)

    print("\n=== Testing LocationExtractor ===\n")
    for query in GOOD_TEST_QUERIES:
        print(f"--- '{query}' ---")
        result = await extractor.extract(query)
        if result.place_name:
            print(f"  Extracted: {result.place_name}")
        else:
            print("  No location found")
        print(f"  Time: {result.extraction_time_ms:.0f}ms\n")

    print("\n=== Testing Geocoder ===\n")
    test_places = [
        "Hawaii",
        "Brazil",
        "Los Angeles",
        "California",
        "Houston, Texas",
        "Australia",
    ]
    for place in test_places:
        print(f"--- '{place}' ---")
        result = await geocoder.geocode(place)
        if result:
            print(f"  Resolved: {result.resolved_name}")
            print(f"  Bbox: {result.bbox}")
            if result.geometry:
                print(f"  Geometry: {result.geometry.get('type')}")
        else:
            print("  Failed")
        print(f"  Time: {result.geocode_time_ms:.0f}ms\n")

    print("\n=== Testing Full Pipeline ===\n")
    for query in GOOD_TEST_QUERIES:
        print(f"--- '{query}' ---")
        result = await parser.parse(query)
        if result.bbox:
            print(f"  Extracted: {result.extracted_place}")
            print(f"  Resolved: {result.resolved_place}")
            print(f"  Bbox: {result.bbox}")
        else:
            print(f"  Error: {result.error}")
        print(f"  Time: {result.total_time_ms:.0f}ms\n")


if __name__ == "__main__":
    asyncio.run(main())
