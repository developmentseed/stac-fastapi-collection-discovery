"""LLM-assisted date parsing for natural language temporal queries."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import date

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import DATE_PARSING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class DateParseResult:
    """Result of parsing a natural language date expression."""

    original_expression: str
    """The original natural language expression."""

    start_date: str | None
    """Start date in ISO-8601 format (YYYY-MM-DD), or None if parsing failed."""

    end_date: str | None
    """End date in ISO-8601 format (YYYY-MM-DD), or None if parsing failed."""

    datetime_range: str | None
    """Formatted as 'start/end' for STAC datetime parameter, or None if parsing failed."""

    error: str | None
    """Error message if parsing failed, None otherwise."""

    parse_time_ms: float
    """Time taken to parse in milliseconds."""

    @property
    def success(self) -> bool:
        """Whether parsing was successful."""
        return self.datetime_range is not None and self.error is None


def validate_datetime_range(start: str, end: str) -> tuple[str | None, str | None]:
    """Validate and normalize an ISO-8601 datetime range.

    Adapted from EIE project's set_datetime tool.

    Args:
        start: Start date in YYYY-MM-DD format
        end: End date in YYYY-MM-DD format

    Returns:
        (datetime_range, error) - datetime_range is 'start/end' if valid, None if invalid
                                  error is None if valid, error message if invalid
    """
    # Validate format
    iso_date_pattern = r"^\d{4}-\d{2}-\d{2}$"

    if not re.match(iso_date_pattern, start):
        return None, f"Invalid start date format: expected YYYY-MM-DD, got '{start}'"

    if not re.match(iso_date_pattern, end):
        return None, f"Invalid end date format: expected YYYY-MM-DD, got '{end}'"

    # Validate date values are real dates
    try:
        start_parts = [int(p) for p in start.split("-")]
        date(start_parts[0], start_parts[1], start_parts[2])
    except ValueError as e:
        return None, f"Invalid start date: {e}"

    try:
        end_parts = [int(p) for p in end.split("-")]
        date(end_parts[0], end_parts[1], end_parts[2])
    except ValueError as e:
        return None, f"Invalid end date: {e}"

    # Validate start <= end
    if end < start:
        return None, (
            f"Invalid date range: end date ({end}) "
            f"must be on or after start date ({start})"
        )

    return f"{start}/{end}", None


def to_rfc3339_interval(date_range: str) -> str:
    """Convert a YYYY-MM-DD/YYYY-MM-DD range to a full RFC3339 interval.

    STAC collection-search requires full RFC3339 timestamps; bare dates
    are rejected with 400 by pgstac-backed catalogs.
    """
    start, end = date_range.split("/")
    if "T" not in start:
        start = f"{start}T00:00:00Z"
    if "T" not in end:
        end = f"{end}T23:59:59Z"
    return f"{start}/{end}"


class DateParser:
    """Parse natural language date expressions into ISO-8601 ranges using an LLM.

    Example:
        ```python
        parser = DateParser(llm_client)
        result = await parser.parse("summer 2020")
        if result.success:
            print(result.datetime_range)  # "2020-06-01/2020-08-31"
        ```
    """

    def __init__(self, client: LLMClient):
        """Initialize the date parser.

        Args:
            client: LLM client for making generation requests
        """
        self._client = client

    async def parse(
        self,
        expression: str,
        reference_date: date | None = None,
    ) -> DateParseResult:
        """Parse a natural language date expression into an ISO-8601 range.

        Args:
            expression: Natural language date expression
                (e.g., "summer 2020", "last year")
            reference_date: Reference date for relative expressions
                (defaults to today)

        Returns:
            DateParseResult with parsed dates or error information
        """
        start_time = time.perf_counter()

        if reference_date is None:
            reference_date = date.today()

        # Format the system prompt with current date
        system_prompt = DATE_PARSING_SYSTEM_PROMPT.format(
            current_date=reference_date.isoformat()
        )

        try:
            response = await self._client.generate(
                prompt=f'Parse this date expression: "{expression}"',
                system=system_prompt,
                json_mode=True,
                temperature=0.0,
                max_tokens=256,
            )

            parse_time_ms = (time.perf_counter() - start_time) * 1000

            # Parse the JSON response
            parsed = response.parse_json()

            if parsed is None:
                logger.warning(
                    f"Failed to parse LLM response as JSON: {response.content}"
                )
                return DateParseResult(
                    original_expression=expression,
                    start_date=None,
                    end_date=None,
                    datetime_range=None,
                    error=f"Failed to parse LLM response: {response.content[:100]}",
                    parse_time_ms=parse_time_ms,
                )

            # Check for error in response
            if "error" in parsed:
                return DateParseResult(
                    original_expression=expression,
                    start_date=None,
                    end_date=None,
                    datetime_range=None,
                    error=parsed["error"],
                    parse_time_ms=parse_time_ms,
                )

            # Extract start and end dates
            start_date = parsed.get("start")
            end_date = parsed.get("end")

            if not start_date or not end_date:
                return DateParseResult(
                    original_expression=expression,
                    start_date=None,
                    end_date=None,
                    datetime_range=None,
                    error="LLM response missing 'start' or 'end' field",
                    parse_time_ms=parse_time_ms,
                )

            # Validate the dates
            datetime_range, validation_error = validate_datetime_range(
                start_date, end_date
            )

            if validation_error:
                return DateParseResult(
                    original_expression=expression,
                    start_date=None,
                    end_date=None,
                    datetime_range=None,
                    error=validation_error,
                    parse_time_ms=parse_time_ms,
                )

            logger.info(
                f"Parsed date expression '{expression}' -> {datetime_range}",
                extra={
                    "expression": expression,
                    "datetime_range": datetime_range,
                    "parse_time_ms": round(parse_time_ms, 2),
                },
            )

            return DateParseResult(
                original_expression=expression,
                start_date=start_date,
                end_date=end_date,
                datetime_range=datetime_range,
                error=None,
                parse_time_ms=parse_time_ms,
            )

        except LLMError as e:
            parse_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM error parsing date expression '{expression}': {e}")
            return DateParseResult(
                original_expression=expression,
                start_date=None,
                end_date=None,
                datetime_range=None,
                error=f"LLM error: {e}",
                parse_time_ms=parse_time_ms,
            )
