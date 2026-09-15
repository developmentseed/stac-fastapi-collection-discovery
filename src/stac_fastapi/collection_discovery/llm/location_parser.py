"""LLM-assisted location parsing with geocoding for natural language spatial queries."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import (
    LOCATION_EXTRACTION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# Minimum bbox size in degrees (~50km) to ensure adequate coverage
MIN_BBOX_SIZE = 0.5


@dataclass
class LocationExtractionResult:
    """Result of extracting a place name from a query."""

    original_query: str
    """The original user query."""

    place_name: str | None
    """Extracted place name, or None if no location found."""

    extraction_time_ms: float
    """Time taken for extraction in milliseconds."""


@dataclass
class GeocodeResult:
    """Result of geocoding a place name."""

    place_name: str
    """The input place name."""

    resolved_name: str
    """Canonical place name from the geocoder."""

    bbox: list[float]
    """Bounding box [west, south, east, north]."""

    geometry: dict[str, Any] | None
    """GeoJSON geometry if available."""

    geocode_time_ms: float
    """Time taken for geocoding in milliseconds."""


@dataclass
class LocationParseResult:
    """Result of the full location parsing pipeline."""

    original_query: str
    """The original user query."""

    extracted_place: str | None
    """Place name extracted by LLM."""

    resolved_place: str | None
    """Canonical place name from geocoder."""

    bbox: list[float] | None
    """Bounding box [west, south, east, north]."""

    geometry: dict[str, Any] | None
    """GeoJSON geometry if available."""

    total_time_ms: float
    """Total pipeline time in milliseconds."""

    error: str | None = None
    """Error message if parsing failed."""


def _ensure_min_bbox(bbox: list[float]) -> list[float]:
    """Expand bbox if smaller than MIN_BBOX_SIZE in either dimension."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lon_size = max_lon - min_lon
    lat_size = max_lat - min_lat

    if lon_size < MIN_BBOX_SIZE:
        center_lon = (min_lon + max_lon) / 2
        min_lon = center_lon - MIN_BBOX_SIZE / 2
        max_lon = center_lon + MIN_BBOX_SIZE / 2

    if lat_size < MIN_BBOX_SIZE:
        center_lat = (min_lat + max_lat) / 2
        min_lat = center_lat - MIN_BBOX_SIZE / 2
        max_lat = center_lat + MIN_BBOX_SIZE / 2

    return [min_lon, min_lat, max_lon, max_lat]


class LocationExtractor:
    """Extract place names from natural language queries using an LLM."""

    def __init__(self, client: LLMClient):
        """Initialize the location extractor.

        Args:
            client: LLM client for making generation requests
        """
        self._client = client

    async def extract(self, query: str) -> LocationExtractionResult:
        """Extract a place name from a natural language query.

        Args:
            query: Natural language query (e.g., "coral bleaching near Hawaii")

        Returns:
            LocationExtractionResult with extracted place name or None
        """
        start_time = time.perf_counter()

        try:
            response = await self._client.generate(
                prompt=f'Extract the place name from this query: "{query}"',
                system=LOCATION_EXTRACTION_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.0,
                max_tokens=128,
            )

            extraction_time_ms = (time.perf_counter() - start_time) * 1000

            parsed = response.parse_json()

            if parsed is None:
                logger.warning(
                    f"Failed to parse LLM response as JSON: {response.content}"
                )
                return LocationExtractionResult(
                    original_query=query,
                    place_name=None,
                    extraction_time_ms=extraction_time_ms,
                )

            place_name = parsed.get("place_name")

            logger.info(
                f"Extracted location from '{query}' -> {place_name}",
                extra={
                    "query": query,
                    "place_name": place_name,
                    "extraction_time_ms": round(extraction_time_ms, 2),
                },
            )

            return LocationExtractionResult(
                original_query=query,
                place_name=place_name,
                extraction_time_ms=extraction_time_ms,
            )

        except LLMError as e:
            extraction_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM error extracting location from '{query}': {e}")
            return LocationExtractionResult(
                original_query=query,
                place_name=None,
                extraction_time_ms=extraction_time_ms,
            )


class Geocoder:
    """Geocode place names to bounding boxes using Nominatim (OpenStreetMap)."""

    def __init__(self, base_url: str = "https://nominatim.openstreetmap.org"):
        """Initialize the geocoder.

        Args:
            base_url: Base URL for the geocoding service
        """
        self._base_url = base_url

    async def geocode(
        self,
        place_name: str,
        timeout: float = 10.0,
    ) -> GeocodeResult | None:
        """Geocode a place name to a bounding box.

        Args:
            place_name: Place name to geocode (e.g., "San Francisco Bay Area")
            timeout: Request timeout in seconds

        Returns:
            GeocodeResult with bbox and geometry, or None if geocoding failed
        """
        start_time = time.perf_counter()

        url = f"{self._base_url}/search"
        params: dict[str, str | int] = {
            "q": place_name,
            "format": "json",
            "limit": 1,
            "polygon_geojson": 1,
        }
        headers = {"User-Agent": "STAC-Collection-Discovery/1.0"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                response.raise_for_status()
                results = response.json()

            geocode_time_ms = (time.perf_counter() - start_time) * 1000

            if not results:
                logger.warning(f"No geocoding results for '{place_name}'")
                return None

            result = results[0]

            # Nominatim returns: [min_lat, max_lat, min_lon, max_lon]
            # Convert to: [west, south, east, north]
            raw_bbox = [
                float(result["boundingbox"][2]),  # min_lon (west)
                float(result["boundingbox"][0]),  # min_lat (south)
                float(result["boundingbox"][3]),  # max_lon (east)
                float(result["boundingbox"][1]),  # max_lat (north)
            ]

            # Use polygon if available, otherwise expand small bboxes
            geojson = result.get("geojson")
            if geojson and geojson.get("type") in {"Polygon", "MultiPolygon"}:
                bbox = raw_bbox
                geometry = geojson
            else:
                bbox = _ensure_min_bbox(raw_bbox)
                center_lon = (raw_bbox[0] + raw_bbox[2]) / 2
                center_lat = (raw_bbox[1] + raw_bbox[3]) / 2
                geometry = {
                    "type": "Point",
                    "coordinates": [center_lon, center_lat],
                }

            logger.info(
                f"Geocoded '{place_name}' -> {result['display_name']}",
                extra={
                    "place_name": place_name,
                    "resolved_name": result["display_name"],
                    "bbox": bbox,
                    "geocode_time_ms": round(geocode_time_ms, 2),
                },
            )

            return GeocodeResult(
                place_name=place_name,
                resolved_name=result["display_name"],
                bbox=bbox,
                geometry=geometry,
                geocode_time_ms=geocode_time_ms,
            )

        except httpx.HTTPError as e:
            geocode_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Geocoding error for '{place_name}': {e}")
            return None


class LocationParser:
    """Full location parsing pipeline: extract place name + geocode to bbox.

    Example:
        ```python
        parser = LocationParser(llm_client, geocoder)
        result = await parser.parse("coral bleaching near Great Barrier Reef")
        if result.bbox:
            print(result.bbox)  # [142.5, -24.0, 154.0, -10.0]
        ```
    """

    def __init__(self, client: LLMClient, geocoder: Geocoder):
        """Initialize the location parser.

        Args:
            client: LLM client for extraction
            geocoder: Geocoder for resolving place names to coordinates
        """
        self._extractor = LocationExtractor(client)
        self._geocoder = geocoder

    async def parse(
        self,
        query: str,
        geocoding_timeout: float = 10.0,
    ) -> LocationParseResult:
        """Parse a natural language query to extract and geocode a location.

        Args:
            query: Natural language query
            geocoding_timeout: Timeout for geocoding requests

        Returns:
            LocationParseResult with bbox, geometry, and metadata
        """
        start_time = time.perf_counter()

        # Step 1: Extract place name using LLM
        extraction = await self._extractor.extract(query)

        if not extraction.place_name:
            return LocationParseResult(
                original_query=query,
                extracted_place=None,
                resolved_place=None,
                bbox=None,
                geometry=None,
                total_time_ms=(time.perf_counter() - start_time) * 1000,
                error="No location found in query",
            )

        # Step 2: Geocode the extracted place name
        geocode = await self._geocoder.geocode(
            extraction.place_name,
            timeout=geocoding_timeout,
        )

        total_time_ms = (time.perf_counter() - start_time) * 1000

        if geocode is None:
            return LocationParseResult(
                original_query=query,
                extracted_place=extraction.place_name,
                resolved_place=None,
                bbox=None,
                geometry=None,
                total_time_ms=total_time_ms,
                error=f"Failed to geocode '{extraction.place_name}'",
            )

        logger.info(
            f"Parsed location from '{query}' -> {geocode.resolved_name} {geocode.bbox}",
            extra={
                "query": query,
                "extracted_place": extraction.place_name,
                "resolved_place": geocode.resolved_name,
                "bbox": geocode.bbox,
                "total_time_ms": round(total_time_ms, 2),
            },
        )

        return LocationParseResult(
            original_query=query,
            extracted_place=extraction.place_name,
            resolved_place=geocode.resolved_name,
            bbox=geocode.bbox,
            geometry=geocode.geometry,
            total_time_ms=total_time_ms,
        )
