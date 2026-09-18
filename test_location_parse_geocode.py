"""Manual demo for location extraction (QueryDecomposer) and geocoding."""

import asyncio

from stac_fastapi.collection_discovery.llm import (
    Geocoder,
    LLMClient,
    QueryDecomposer,
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
    decomposer = QueryDecomposer(client)

    print("\n=== Testing Location Extraction (QueryDecomposer) ===\n")
    for query in GOOD_TEST_QUERIES:
        print(f"--- '{query}' ---")
        result = await decomposer.decompose(query)
        if result.location:
            print(f"  Extracted: {result.location}")
        else:
            print("  No location found")
        print(f"  Time: {result.decompose_time_ms:.0f}ms\n")

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
            print(f"  Time: {result.geocode_time_ms:.0f}ms\n")
        else:
            print("  Failed\n")

    print("\n=== Testing Full Chain (decompose -> geocode) ===\n")
    for query in GOOD_TEST_QUERIES:
        print(f"--- '{query}' ---")
        decomposed = await decomposer.decompose(query)
        if not decomposed.location:
            print("  No location found\n")
            continue
        geocode = await geocoder.geocode(decomposed.location)
        if geocode:
            print(f"  Extracted: {decomposed.location}")
            print(f"  Resolved: {geocode.resolved_name}")
            print(f"  Bbox: {geocode.bbox}\n")
        else:
            print(f"  Failed to geocode '{decomposed.location}'\n")


if __name__ == "__main__":
    asyncio.run(main())
