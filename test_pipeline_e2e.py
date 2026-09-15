"""Manual end-to-end test for the LLM-assisted search pipeline.

Exercises the full AssistedSearchPipeline against real upstream catalogs:
decompose -> date parse -> geocode -> expand -> federated search -> rerank.

Requires LLM_PROVIDER and LLM_API_KEY env vars. Not for CI.
"""

import asyncio

from stac_fastapi.collection_discovery.pipeline import AssistedSearchPipeline
from stac_fastapi.collection_discovery.settings import Settings

# Upstream STAC APIs that support `q` free-text search on /collections:
# CMR LP/POCLOUD: NASA land/ocean DAACs (MODIS, VIIRS, MUR SST, fire)
# openveda: NASA VEDA disaster collections  maap: biomass/forestry
# eoapi: MAXAR disaster-event collections
DEFAULT_APIS = [
    "https://cmr.earthdata.nasa.gov/stac/LPCLOUD",
    "https://cmr.earthdata.nasa.gov/stac/POCLOUD",
    "https://openveda.cloud/api/stac",
    "https://stac.maap-project.org",
    "https://stac.eoapi.dev",
]


def print_result(result) -> None:
    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    d = result.decomposed
    print(f"Query:     {result.query}")
    if d:
        print(f"Topic:     {d.topic}")
        print(f"Location:  {d.location} -> {result.resolved_place}")
        print(f"Date expr: {d.date_expression}")
    print(f"Datetime:  {result.datetime_range or 'None'}")
    print(f"Bbox:      {result.bbox or 'None'}")
    print(f"Terms:     {result.expanded_terms}")
    print(f"Per-API:   {result.per_api_counts}")
    print(f"Ranked:    {len(result.matches)} of {result.candidate_count}")
    print(f"Time:      {result.total_time_ms:.0f}ms")

    if result.errors:
        print(f"Errors:    {result.errors}")

    for i, m in enumerate(result.matches[:10], 1):
        title = m.collection.get("title", m.collection.get("id", "Unknown"))
        source = (m.source_api or "").replace("https://", "").split("/")[0]
        score = f"{m.score}/10" if m.score is not None else "-"
        print(f"  {i}. [{source}] {title[:58]}")
        print(f"      score={score}  via '{m.matched_term}'  {m.reason or ''}")


async def main():
    settings = Settings()
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    apis = settings.upstream_api_urls or DEFAULT_APIS
    print(f"Upstream APIs: {apis}")

    pipeline = AssistedSearchPipeline(settings)

    # Queries matched to actual catalog holdings:
    # POCLOUD: MUR/OSTIA/MODIS/VIIRS SST, chlorophyll, ocean color
    # LPCLOUD: MODIS/VIIRS fire (MOD14/VNP14), NDVI (MOD13), ECOSTRESS
    # openveda: wildfires (caldor/campfire), floods, earthquakes
    # eoapi: MAXAR disasters (hurricanes, floods, fires, earthquakes)
    # maap: biomass (GEDI/ICESat2/ESACCI), forest change (glad/GFC)
    test_queries = [
        "sea surface temperature near Hawaii",
        "wildfires in California 2023",
        "forest biomass",
        "hurricane damage in Florida 2022",
        "ocean chlorophyll",
        "flooding in Libya September 2023",
    ]

    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: '{query}'")
        print(f"{'='*60}")
        result = await pipeline.search(query, apis=apis)
        print_result(result)
        print("\n" + "-" * 60)


if __name__ == "__main__":
    asyncio.run(main())
