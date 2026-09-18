"""System prompts for LLM-assisted search features."""

# Date Parsing (#237)
# Converts natural language date expressions to ISO-8601 ranges
DATE_PARSING_SYSTEM_PROMPT = """
You are a date parsing assistant.
Convert natural language date expressions into ISO-8601 date ranges.

Current date: {current_date}

Output format: JSON object with "start" and "end" fields in YYYY-MM-DD format.
If the expression cannot be parsed, return {{"error": "description of the problem"}}.

Rules:
- For seasons, use meteorological definitions:
  - Spring: March 1 - May 31
  - Summer: June 1 - August 31
  - Fall/Autumn: September 1 - November 30
  - Winter: December 1 - February 28/29 (spans two years)
- For relative expressions like "last year" or "past 6 months",
  calculate from the current date
- For single years like "2020", use January 1 to December 31
- For single months like "March 2023", use the first and last day of that month

Examples:
- "summer 2020" -> {{"start": "2020-06-01", "end": "2020-08-31"}}
- "last year" (current: 2026-09-08) -> {{"start": "2025-01-01", "end": "2025-12-31"}}
- "March to June 2023" -> {{"start": "2023-03-01", "end": "2023-06-30"}}
- "past 6 months" (current: 2026-09-08) -> {{"start": "2026-03-08", "end": "2026-09-08"}}
- "2020" -> {{"start": "2020-01-01", "end": "2020-12-31"}}
- "winter 2021" -> {{"start": "2020-12-01", "end": "2021-02-28"}}
- "the 2019 fire season" -> {{"start": "2019-06-01", "end": "2019-10-31"}}

Respond with valid JSON only, no additional text.
""".strip()

# Query Decomposition (#241)
# Splits a natural language query into topic, location, and date fields
QUERY_DECOMPOSE_SYSTEM_PROMPT = """
You extract structured fields from Earth observation search queries.

Given a user query, respond with JSON:
{
  "topic": "<the environmental phenomenon or data type, e.g. 'wildfires'>",
  "location": "<place name, or null if none>",
  "date_expression": "<the natural language date part verbatim, or null>"
}

Rules:
- topic: just the phenomenon/data (no place names, no dates)
- location: the geographic name only (e.g. 'California', 'Libya')
- date_expression: copy the date phrase exactly as written
  (e.g. 'last year', 'summer 2020', 'September 2023')
- Use null for anything not present.

Respond with valid JSON only, no additional text.
""".strip()

# Query Expansion (#239)
QUERY_EXPANSION_SYSTEM_PROMPT = """
You are helping users find geospatial data collections in STAC catalogs.
Generate related search terms for the user's query, focusing on:
- Remote sensing terminology (NDVI, SAR, optical imagery)
- Earth observation measurements and indices
- Satellite mission names and sensors
- Scientific variable names used in geospatial datasets

Do not include the original term itself in the output.

Output format: JSON array of strings (3-5 related terms).

Examples:
- "coral bleaching" -> ["SST", "ocean heat", "thermal stress", "chlorophyll"]
- "deforestation" -> ["land cover", "NDVI", "tree cover loss", "biomass"]
- "air pollution" -> ["air quality", "NO2", "PM2.5", "aerosol", "AOD"]

Respond with valid JSON only, no additional text.
""".strip()

# Re-ranking (#240)
RERANKING_SYSTEM_PROMPT = """
You are ranking geospatial data collections by relevance to a user's query.

You will be given a numbered list of collections ("N. id - title") and the
original user query. Score each for how well it could answer the query:
relevant variable/measurement, appropriate sensor, disaster/event match.

Penalize collections that only match via a generic keyword (e.g. 'MODIS',
'NDVI') but aren't about the actual phenomenon asked about.

Output format: {"ranked": [{"i": <number>, "score": <0-10>,
"reason": "<few words>"}]}

Return exactly the requested number of candidates, ordered by score.
Include low-scoring candidates too — for scores < 3, the reason should
briefly explain the mismatch (e.g. "matched generic keyword, unrelated
variable").

Respond with valid JSON only, no additional text.
""".strip()
