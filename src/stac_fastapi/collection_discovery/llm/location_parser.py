"""Geocoding for natural language spatial queries via Nominatim (OpenStreetMap)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Minimum bbox size in degrees (~50km) to ensure adequate coverage
MIN_BBOX_SIZE = 0.5


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
