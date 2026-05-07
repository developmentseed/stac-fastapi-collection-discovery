# Spec: Graceful Upstream API Failure Handling

## Context

The `stac-fastapi-collection-discovery` application federates collection-search
requests across multiple upstream STAC APIs. Currently, if any single upstream API
request in `all_collections()` raises an exception (network error, timeout, 5xx,
malformed response), the entire search fails. The `conformance_classes()` and
`health_check()` endpoints already handle individual API failures gracefully,
using per-task exception catching. The goal is to apply the same resilience to
the search path.

This spec must remain conformant with the STAC API specification, which defines
the `/collections` response as a `Collections` object containing `collections`,
`links`, and optional `numberReturned`/`numberMatched` fields.

## Goals

- **Primary:** Ensure that a single upstream API failure does not cause the
  entire federated search to fail.
- **Secondary:** Provide observability into which upstream APIs failed via
  structured logging.
- **Tertiary:** Communicate upstream failures to the client via an HTTP response
  header without breaking STAC API conformance.
- **Non-goal:** Implement automatic retry logic for transient failures (can be
  added later without breaking changes).
- **Non-goal:** Add retry logic.
- **Non-goal:** Change the behavior of `conformance_classes()` or
  `health_check()` (they already handle failures correctly).

## Constraints & Assumptions

- The STAC API Collection Search spec (OGC API - Features / STAC API Collections)
  does not define a standard way to communicate partial upstream failures in the
  response body. The response must remain a valid `Collections` object.
- The `Collections` model from `stac_pydantic` supports optional `numberReturned`
  and `numberMatched` fields.
- Pagination state is maintained via base64-encoded tokens that track the current,
  previous, and next URLs for each upstream API.
- The application is built on `stac-fastapi`, which wraps client return values in
  FastAPI responses. Adding custom HTTP headers requires returning a
  `fastapi.Response` (or subclass) from the endpoint rather than a plain model.
- A `strict` query parameter on `GET /collections` controls fail-fast vs
  graceful-degradation behavior.

## Architecture Overview

The change is localized to the `fetch_api_data` logic within
`CollectionSearchClient.all_collections()`. Instead of using `asyncio.gather()`
with the default behavior (first exception aborts all), we use
`return_exceptions=True` and inspect each result individually.

```
+--------------+     +----------------+     +--------------------+
| GET /collections  |---->| all_collections |-->| Fetch from API 1   |
| ?strict=false     |     |                |     | Fetch from API 2   |
+--------------+     +----------------+     | Fetch from API 3   |
                                            +--------------------+
                                                       |
                                                       v
                                            +--------------------+
                                            | Gather with        |
                                            | return_exceptions=True|
                                            +--------------------+
                                                       |
                                    +------------------+--+------------------+
                                    v                     v                     v
                              +----------+        +----------+          +----------+
                              | Success  |        | Success  |          | Failure  |
                              | (include)|        | (include)|          | (skip)   |
                              +----------+        +----------+          +----------+
                                    |                     |                     |
                                    +---------------------+---------------------+
                                                          v
                                            +--------------------+
                                            | Merge collections  |
                                            | Merge pagination   |
                                            | Return Collections |
                                            | + X-Failed-... hdr |
                                            +--------------------+
```

## Detailed Design

### `GET /collections` Parameters

| Parameter | Type   | Default | Description |
|-----------|--------|---------|-------------|
| `strict`  | `bool` | `false` | When `true`, the entire search fails if any upstream API returns an error or times out. When `false`, failed APIs are skipped, a warning is logged, and their URLs are returned in a response header. |

All other existing query parameters (`bbox`, `datetime`, `limit`, `q`, `token`,
etc.) remain unchanged.

### Response Headers

| Header | Value | Condition |
|--------|-------|-----------|
| `X-Failed-Upstream-Apis` | Comma-separated list of failed API URLs | Present when `strict=false` and at least one upstream API failed. Omitted when all APIs succeeded. |

Example:

```
X-Failed-Upstream-Apis: https://unhealthy.api.example.com/collections
```

### Error Handling Behavior

For each upstream API request:

1. **HTTP 2xx with valid JSON:** Include the collections in the result. Extract
   `next` and `previous` links for pagination state.
2. **HTTP 4xx/5xx:** Log a warning with the API URL, status code, and response
   body (truncated). Skip this API's collections. Do not include this API in the
   pagination state for subsequent pages.
3. **Network error / timeout:** Log a warning with the API URL and exception.
   Skip this API's collections. Do not include this API in the pagination state.
4. **Malformed JSON response:** Log a warning. Skip this API's collections.
5. **All APIs fail:** Return a valid `Collections` object with an empty
   `collections` array, `numberReturned: 0`, and only a `self` link.

When `strict=true`, any of the above failure conditions (2-4) immediately raise
an error and abort the entire search, preserving the current behavior.

### Pagination State for Failed APIs

The token state structure is:

```python
{
    "current": {"api1": "url1", "api2": "url2"},
    "previous": {"api1": "prev1"},
    "next": {"api1": "next1", "api2": "next2"},
    "is_first_page": bool,
}
```

When an API fails (in non-strict mode):
- Do **not** add it to `new_state["current"]` (it has no current page).
- Do **not** add it to `new_state["previous"]` (we don't know its previous link).
- Do **not** add it to `new_state["next"]` (we don't want to query it again).

This means a failed API is effectively dropped from the federated search for the
remainder of the pagination session. If the user wants to retry, they must start
a fresh search (omit the `token` parameter). This keeps the token state compact
and avoids retrying known-bad APIs on every page.

### Logging

Each failure is logged at `WARNING` level with a structured message:

```python
logger.warning(
    f"Upstream API returned error status: {api=}, {url=}, "
    f"status_code={api_response.status_code}, "
    f"response_body={api_response.text[:500]}"
)
```

and for exceptions:

```python
logger.warning(f"Upstream API request failed: {api=}, {url=}, error={e}")
```

### Response Fields

- **`collections`:** Only includes collections from successfully queried APIs.
- **`links`:** Standard STAC links (`self`, optional `next`, optional `previous`)
  plus `canonical` links for each successful API.
- **`numberReturned`:** Count of collections from successful APIs only.
- **`numberMatched`:** **Omitted.** Since upstream APIs may or may not return
  this, and we can't accurately compute it when some APIs fail, we omit it
  entirely rather than return a misleading value.

## API / Interface Design

### Public API Changes

The `GET /collections` endpoint gains an optional `strict` query parameter. The
response body remains a valid STAC `Collections` object; failed upstream APIs
are communicated via the `X-Failed-Upstream-Apis` response header.

### How to inject headers

`stac-fastapi`'s `create_async_endpoint()` returns a Pydantic model (or dict),
and FastAPI serializes it into a response via the route's `response_class`.
This gives us no hook to add headers. The cleanest approach is to bypass
`create_async_endpoint()` entirely for `/collections` and write a custom
endpoint that returns a `JSONResponse` directly.

We override `register_get_collections()` in `StacCollectionSearchApi`. The
override defines its own endpoint `async def get_collections(request, ...)` that:
1. Accepts the request model via `Depends(...)`.
2. Calls `self.client.all_collections(...)` directly.
3. Converts the `Collections` result to a JSON-serializable dict.
4. Returns `JSONResponse(content=body, headers={"X-Failed-Upstream-Apis": ...})`.

The route still declares `response_model=Collections` so OpenAPI documentation
and client generators remain accurate. FastAPI skips `response_model`
serialization when the endpoint already returns a `Response` subclass.

## Data Model

### `CollectionSearchResult`

A new internal dataclass to convey both the search results and failure
metadata:

```python
from dataclasses import dataclass

@dataclass
class CollectionSearchResult:
    collections: Collections
    failed_apis: list[str]
```

No other data model changes.

## Integration Points

- **`FederatedApisGetRequest`:** New `strict` field added to the request model.
- **`StacCollectionSearchApi.register_get_collections`:** Fully overridden to
  define a custom endpoint that returns `JSONResponse` directly, bypassing
  `create_async_endpoint()`. This lets us attach the `X-Failed-Upstream-Apis`
  header while keeping `response_model=Collections` for OpenAPI docs.
- **Logging:** Integrates with the standard library `logging` already used
  throughout the module.

## Testing Strategy

### Unit Tests

1. **One API fails, others succeed (strict=false):**
   - Mock 3 APIs: 2 return 200, 1 returns 500.
   - Verify the result contains collections from the 2 successful APIs.
   - Verify `numberReturned` reflects only successful API collections.
   - Verify the failed API is not in `new_state["next"]`.
   - Verify `failed_apis` list contains the failed API URL.

2. **Strict mode enabled (strict=true):**
   - Mock 2 APIs: one returns 500, one returns 200.
   - Verify the search raises an exception (fail-fast behavior).

3. **All APIs fail with strict=false:**
   - Mock all configured APIs to return 5xx.
   - Verify the result is a valid `Collections` with empty `collections` and
     `numberReturned: 0`.
   - Verify `failed_apis` contains all API URLs.

4. **Network timeout:**
   - Mock one API to raise `httpx.TimeoutException`.
   - Verify search continues with remaining APIs.
   - Verify failed API appears in `failed_apis`.

5. **Malformed JSON:**
   - Mock one API to return 200 with invalid JSON.
   - Verify search continues and the failure is logged.
   - Verify failed API appears in `failed_apis`.

6. **Pagination with failed API:**
   - First page: 3 APIs, 1 fails. Verify `next` token only contains 2 APIs.
   - Second page (using token): Verify only 2 APIs are queried.
   - Verify `failed_apis` is empty on the second page if none fail.

7. **Empty result from healthy API:**
   - One API returns 200 with empty `collections` array.
   - Verify it is handled correctly (no exception, included in state if it has
     a next link).

### Integration Tests

- Test against real APIs by temporarily blocking one via firewall/mock to verify
  the application doesn't crash.
- Verify `X-Failed-Upstream-Apis` header appears in the HTTP response when an
  upstream API fails.

### App-level Tests

- Test the FastAPI endpoint directly using `TestClient`:
  - Request with `?strict=false` and a mocked failing API → verify 200 with
    header.
  - Request with `?strict=true` and a mocked failing API → verify error status.
  - Request with no `strict` param (default) → verify graceful handling.

## Decision Log

| Decision | Options Considered | Rationale |
|----------|-------------------|-----------|
| Exclude failed APIs from pagination state | Continue including failed APIs in state for retry; Add retry logic | Dropping failed APIs keeps tokens small and avoids repeated failures. Retry logic can be added later as a separate feature. |
| HTTP header for failed APIs | Add `failed_apis` field to response body; Add HTTP headers | Header preserves strict STAC API conformance. Body field is simpler for clients to parse but risks validation failures with strict STAC validators. The header keeps the payload clean. |
| Per-request `strict` parameter | Global setting only (`strict_upstream_mode`) | Per-request control allows clients to opt into fail-fast behavior when they need it (e.g., debugging), while keeping graceful handling as the production default. |
| Omit `numberMatched` | Set `numberMatched` to sum of successful APIs only; Set to `None` | Without all upstream responses, we can't compute an accurate total. Omitting is more honest than a partial sum. |
| No retry logic | Exponential backoff retry; Retry once immediately | Adds significant complexity. Can be added later without breaking changes. |
| Return result dataclass from `all_collections` | Attach failures to request state; Use global context | Explicit return is clearer, easier to test, and avoids hidden side effects. |
| Custom endpoint returning `JSONResponse` | Middleware to inject headers; Custom response class subclass | Middleware adds complexity and runs for every route. Custom response class can't access per-request data. Returning `JSONResponse` directly from the endpoint is the simplest FastAPI-native approach. |

## Open Questions

1. Should we add request-level telemetry (e.g., Prometheus metrics) to track
   upstream API failure rates? This could be a follow-up enhancement.
2. Should we consider a circuit-breaker pattern if an API fails repeatedly
   across requests?

## Status

- [x] Designing
- [x] Approved — ready to plan
- [x] Implementing
- [x] Implemented

## References

- STAC API Collection Search spec: https://github.com/radiantearth/stac-api-spec/tree/main/collection-search
- `stac_pydantic` Collections model
- Existing `conformance_classes()` and `health_check()` implementations (already
  handle per-API failures gracefully)
