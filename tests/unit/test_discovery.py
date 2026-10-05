import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stac_fastapi.collection_discovery.discovery import (
    DISCOVERY_CONFORMANCE_CLASS,
    build_discovery_router,
    discovery_conformance_classes,
    discovery_enabled,
    discovery_links,
    get_llm,
)
from stac_fastapi.collection_discovery.llm.client import LLMError
from stac_fastapi.collection_discovery.settings import Settings

GEO = "https://geo.example"
# Substrings that identify each pipeline step's system prompt (see StubLLM routes)
DECOMPOSE = "extract structured fields"
EXPAND = "helping users find geospatial"
DATE = "date parsing assistant"
RERANK = "ranking geospatial"
SECRET = "sk-secret"
INTERPRET = "/discovery/interpret"
RANK = "/discovery/rank"

CALIFORNIA = [
    {
        "display_name": "California, United States",
        "boundingbox": ["32.5", "42.0", "-124.4", "-114.1"],
        "geojson": {"type": "Polygon", "coordinates": []},
    }
]

FULL_ROUTES = {
    DECOMPOSE: {
        "topic": "wildfires",
        "location": "California",
        "date_expression": "2023",
    },
    EXPAND: ["burned area", "fire"],
    DATE: {"start": "2023-01-01", "end": "2023-12-31"},
}
TOPIC_ROUTES = {
    DECOMPOSE: {"topic": "t", "location": None, "date_expression": None},
    EXPAND: [f"e{i}" for i in range(20)],
}


def make_client(stub=None, **settings_kwargs) -> TestClient:
    settings = Settings(llm_provider="openai", llm_api_key="test-key", **settings_kwargs)
    app = FastAPI()
    app.state.settings = settings
    app.include_router(build_discovery_router())
    if stub is not None:
        app.dependency_overrides[get_llm] = lambda: stub
    return TestClient(app)


def misconfigured_client() -> TestClient:
    app = FastAPI()
    app.state.settings = Settings()  # no provider/key
    app.include_router(build_discovery_router())
    return TestClient(app)


def interpret(client, query="q", **extra):
    return client.post(INTERPRET, json={"query": query, **extra})


def rank_body(*ids, **extra):
    return {"query": "wildfires", "candidates": [{"id": i} for i in ids], **extra}


def candidate_ids(n):
    return [f"c{i}" for i in range(n)]


def scored_all(n):
    return {
        RERANK: {"ranked": [{"i": i + 1, "score": 5, "reason": "r"} for i in range(n)]}
    }


# --- /discovery/interpret ---


@respx.mock
def test_interpret_full_query(make_stub_llm):
    respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=CALIFORNIA))
    client = make_client(make_stub_llm(FULL_ROUTES), geocoding_service_url=GEO)
    r = interpret(client, "wildfires in California 2023")
    assert r.status_code == 200
    body = r.json()
    assert body["q"] == ["wildfires", "burned area", "fire"]
    assert body["bbox"] == [-124.4, 32.5, -114.1, 42.0]
    assert body["datetime"].startswith("2023-01-01")
    assert body["datetime"].endswith("2023-12-31T23:59:59Z")
    assert body["warnings"] == []


def test_interpret_without_location_or_date(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "sst", "location": None, "date_expression": None},
        EXPAND: ["sea surface temperature"],
    }
    body = interpret(make_client(make_stub_llm(routes)), "sst").json()
    assert body["q"] == ["sst", "sea surface temperature"]
    assert body["bbox"] is None and body["datetime"] is None and body["warnings"] == []


def test_interpret_geocoding_not_configured_warns_and_makes_no_request(make_stub_llm):
    with respx.mock(assert_all_called=False) as router:
        client = make_client(make_stub_llm(FULL_ROUTES))  # no geocoding_service_url
        body = interpret(client).json()
        assert router.calls.call_count == 0
    assert body["bbox"] is None
    assert any("geocoding" in w for w in body["warnings"])
    assert body["datetime"] is not None  # other steps still succeed


@pytest.mark.parametrize(
    "geocoder_reply",
    [
        [{"display_name": "X"}],
        [{"boundingbox": ["1", "2", "3", "4"], "display_name": "X", "geojson": "str"}],
    ],
    ids=["missing-boundingbox", "non-dict-geojson"],
)
@respx.mock
def test_interpret_malformed_geocoder_response_is_a_warning_not_500(
    make_stub_llm, geocoder_reply
):
    respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=geocoder_reply))
    client = make_client(make_stub_llm(FULL_ROUTES), geocoding_service_url=GEO)
    r = interpret(client)
    assert r.status_code == 200
    assert r.json()["bbox"] is None
    assert any("California" in w for w in r.json()["warnings"])


def test_interpret_date_parse_failure_is_a_warning(make_stub_llm):
    routes = {**FULL_ROUTES, DATE: {"error": "cannot parse"}}
    body = interpret(make_client(make_stub_llm(routes))).json()
    assert body["datetime"] is None
    assert "date parsing failed" in body["warnings"]
    assert "cannot parse" not in str(body)


@pytest.mark.parametrize(
    "date_reply",
    [[1, 2], {"start": 2023, "end": 2024}],
    ids=["list", "non-string-values"],
)
def test_interpret_malformed_date_output_is_a_warning_not_500(make_stub_llm, date_reply):
    r = interpret(make_client(make_stub_llm({**FULL_ROUTES, DATE: date_reply})))
    assert r.status_code == 200
    assert r.json()["datetime"] is None
    assert any("date" in w for w in r.json()["warnings"])


def test_interpret_unparseable_expansion_keeps_topic_only(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "wildfires", "location": None, "date_expression": None},
        EXPAND: "not json",
    }
    body = interpret(make_client(make_stub_llm(routes)), "wildfires").json()
    assert body["q"] == ["wildfires"]
    assert any("expansion" in w for w in body["warnings"])


@pytest.mark.parametrize(
    "fields",
    [
        {"topic": ["fire"], "location": None, "date_expression": None},
        {"topic": 42, "location": None, "date_expression": None},
        {"topic": "fire", "location": ["California"], "date_expression": None},
        {"topic": "fire", "location": 7, "date_expression": None},
        {"topic": "fire", "location": None, "date_expression": ["2023"]},
        {"topic": "fire", "location": None, "date_expression": 2023},
    ],
    ids=[
        "topic-list",
        "topic-int",
        "location-list",
        "location-int",
        "date-list",
        "date-int",
    ],
)
def test_interpret_non_string_decomposer_fields_never_500(make_stub_llm, fields):
    routes = {DECOMPOSE: fields, EXPAND: ["burned area"], DATE: {"error": "x"}}
    r = interpret(make_client(make_stub_llm(routes)))
    assert r.status_code == 200
    assert all(isinstance(t, str) for t in r.json()["q"])


@respx.mock
def test_interpret_without_topic_returns_empty_q_but_resolves_bbox_and_datetime(
    make_stub_llm,
):
    routes = {
        DECOMPOSE: {"topic": None, "location": "California", "date_expression": "2023"},
        DATE: {"start": "2023-01-01", "end": "2023-12-31"},
    }
    stub = make_stub_llm(routes)
    respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=CALIFORNIA))
    r = interpret(make_client(stub, geocoding_service_url=GEO), "California 2023")
    body = r.json()
    assert r.status_code == 200
    assert body["q"] == []
    assert body["bbox"] == [-124.4, 32.5, -114.1, 42.0]
    assert body["datetime"] is not None
    assert any("no topic" in w for w in body["warnings"])
    assert not any(EXPAND in (c["system"] or "") for c in stub.calls)


@pytest.mark.parametrize(
    ("topic", "extra"),
    [("   ", {}), ("", {"max_terms": 1})],
    ids=["blank-topic", "empty-topic-with-max_terms"],
)
def test_interpret_blank_topic_is_treated_as_no_topic(make_stub_llm, topic, extra):
    routes = {DECOMPOSE: {"topic": topic, "location": None, "date_expression": None}}
    r = interpret(make_client(make_stub_llm(routes)), **extra)
    assert r.status_code == 200
    assert r.json()["q"] == [] and any("no topic" in w for w in r.json()["warnings"])


# --- /discovery/interpret: client-chosen max_terms ---


@pytest.mark.parametrize(
    ("settings", "extra", "expected_len"),
    [
        ({}, {}, 10),
        ({}, {"max_terms": None}, 10),
        ({}, {"max_terms": 3}, 3),
        ({"discovery_max_terms": 15}, {"max_terms": 15}, 15),
        ({"discovery_max_terms": 4}, {}, 4),
    ],
    ids=["default-10", "null-uses-default", "explicit", "at-ceiling", "default-clamped"],
)
def test_interpret_max_terms_sets_q_length(make_stub_llm, settings, extra, expected_len):
    r = interpret(make_client(make_stub_llm(TOPIC_ROUTES), **settings), "t", **extra)
    assert r.status_code == 200
    assert r.json()["q"] == ["t", *(f"e{i}" for i in range(expected_len - 1))]


def test_interpret_max_terms_1_skips_expansion_call(make_stub_llm):
    stub = make_stub_llm(TOPIC_ROUTES)
    r = interpret(make_client(stub), "t", max_terms=1)
    assert r.status_code == 200 and r.json()["q"] == ["t"]
    assert r.json()["warnings"] == []
    assert len(stub.calls) == 1 and DECOMPOSE in stub.calls[0]["system"]


# --- /discovery/rank ---


def test_rank_returns_refs_scores_reasons_best_first(make_stub_llm):
    stub = make_stub_llm(
        {
            RERANK: {
                "ranked": [
                    {"i": 1, "score": 3, "reason": "weak"},
                    {"i": 2, "score": 9, "reason": "strong"},
                ]
            }
        }
    )
    body = {
        "query": "wildfires",
        "candidates": [
            {"ref": "https://a/collections/x", "id": "x", "title": "X"},
            {"id": "y", "title": "Y"},
        ],
    }
    r = make_client(stub).post(RANK, json=body)
    assert r.status_code == 200
    assert r.json() == {
        "ranked": [
            {"ref": "y", "score": 9.0, "reason": "strong"},
            {"ref": "https://a/collections/x", "score": 3.0, "reason": "weak"},
        ],
        "scored_count": 2,
        "unscored_count": 0,
        "warnings": [],
    }


def test_rank_presorts_by_matched_terms_and_reports_unscored(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": [{"i": 1, "score": 8, "reason": "ok"}]}})
    body = {
        "query": "q",
        "candidates": [{"id": "a"}, {"id": "b", "matched_terms": ["t1", "t2"]}],
        "max_scored": 1,
    }
    r = make_client(stub).post(RANK, json=body)
    assert [x["ref"] for x in r.json()["ranked"]] == ["b", "a"]
    assert r.json()["ranked"][1]["score"] is None
    assert r.json()["unscored_count"] == 1
    prompt = stub.calls[0]["prompt"]
    assert "1. b - " in prompt and "a - " not in prompt  # only b is in the window


def test_rank_duplicate_effective_refs_are_422(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": []}})
    body = {
        "query": "q",
        "candidates": [{"id": "same"}, {"id": "same", "title": "from another api"}],
    }
    r = make_client(stub).post(RANK, json=body)
    assert r.status_code == 422 and "same" in r.text and stub.calls == []


def test_rank_duplicate_refs_detail_is_bounded(make_stub_llm):
    ids = [f"dup{i}-" + "x" * 200 for i in range(8)]
    body = {"query": "q", "candidates": [{"id": i} for i in ids for _ in range(2)]}
    r = make_client(make_stub_llm({RERANK: {"ranked": []}})).post(RANK, json=body)
    detail = r.json()["detail"]
    assert r.status_code == 422
    assert "8" in detail
    assert "dup0-" in detail and "dup1-" not in detail  # first (sorted) example only
    assert "x" * 101 not in detail
    assert len(detail) < 300


def test_rank_distinct_refs_allow_same_id(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": []}})
    body = {
        "query": "q",
        "candidates": [{"id": "same", "ref": "a|same"}, {"id": "same", "ref": "b|same"}],
    }
    assert make_client(stub).post(RANK, json=body).status_code == 200


def test_rank_rejects_full_collection_objects(make_stub_llm):
    body = {
        "query": "q",
        "candidates": [{"id": "a", "title": "A", "extent": {"spatial": {}}, "links": []}],
    }
    r = make_client(make_stub_llm({RERANK: {"ranked": []}})).post(RANK, json=body)
    assert r.status_code == 422


def test_rank_empty_candidates_is_200_and_makes_no_llm_call(make_stub_llm):
    stub = make_stub_llm({})
    r = make_client(stub).post(RANK, json={"query": "q", "candidates": []})
    assert r.status_code == 200
    assert r.json() == {
        "ranked": [],
        "scored_count": 0,
        "unscored_count": 0,
        "warnings": [],
    }
    assert stub.calls == []


@pytest.mark.parametrize(
    ("stub_args", "warning"),
    [
        (({}, LLMError(f"bad key {SECRET}")), "rerank: LLM call failed"),
        (({RERANK: "not json"}, None), "rerank: LLM returned no usable scores"),
    ],
    ids=["llm-error", "non-json-reply"],
)
def test_rank_llm_failure_returns_200_unscored_with_fixed_warning(
    make_stub_llm, stub_args, warning
):
    r = make_client(make_stub_llm(*stub_args)).post(RANK, json=rank_body("a", "b"))
    assert r.status_code == 200
    assert [x["score"] for x in r.json()["ranked"]] == [None, None]
    assert r.json()["unscored_count"] == 2
    assert r.json()["warnings"] == [warning]
    assert SECRET not in r.text


# --- /discovery/rank: client-chosen max_scored ---


@pytest.mark.parametrize(
    ("n_candidates", "extra", "ceiling", "scored"),
    [
        (80, {}, 100, 50),
        (60, {"max_scored": None}, 100, 50),
        (5, {"max_scored": 2}, 100, 2),
        (3, {"max_scored": 90}, 100, 3),
        (30, {}, 20, 20),
    ],
    ids=[
        "default-50",
        "null-uses-default",
        "explicit",
        "larger-than-candidates",
        "default-clamped",
    ],
)
def test_rank_max_scored_sets_scored_window(
    make_stub_llm, n_candidates, extra, ceiling, scored
):
    stub = make_stub_llm(scored_all(scored))
    body = rank_body(*candidate_ids(n_candidates), **extra)
    r = make_client(stub, discovery_max_scored=ceiling).post(RANK, json=body)
    assert r.status_code == 200
    assert r.json()["scored_count"] == scored
    assert r.json()["unscored_count"] == n_candidates - scored
    prompt = stub.calls[0]["prompt"]
    assert f"{scored}. " in prompt and f"{scored + 1}. " not in prompt


# --- both endpoints: validation ---


@pytest.mark.parametrize("path", [INTERPRET, RANK])
@pytest.mark.parametrize("query", ["", "   ", "x" * 1001], ids=["empty", "blank", "long"])
def test_blank_or_overlong_query_is_422_before_calling_llm(make_stub_llm, path, query):
    stub = make_stub_llm(FULL_ROUTES)
    body = {"query": query, "candidates": [{"id": "a"}]}
    r = make_client(stub).post(path, json=body if path == RANK else {"query": query})
    assert r.status_code == 422 and stub.calls == []


def test_interpret_rejects_unknown_fields(make_stub_llm):
    assert interpret(make_client(make_stub_llm(FULL_ROUTES)), extra=1).status_code == 422


@pytest.mark.parametrize(
    ("path", "body", "settings", "ceiling_numbers"),
    [
        (
            INTERPRET,
            {"query": "t", "max_terms": 40},
            {"discovery_max_terms": 25},
            "40 25",
        ),
        (
            RANK,
            rank_body("a", "b", "c", max_scored=30),
            {"discovery_max_scored": 20},
            "30 20",
        ),
        (RANK, rank_body("a", "b", "c"), {"discovery_max_candidates": 2}, ""),
    ],
    ids=["max_terms", "max_scored", "candidate-count"],
)
def test_value_above_ceiling_is_422_before_calling_llm(
    make_stub_llm, path, body, settings, ceiling_numbers
):
    stub = make_stub_llm({**TOPIC_ROUTES, **scored_all(3)})
    r = make_client(stub, **settings).post(path, json=body)
    assert r.status_code == 422
    for number in ceiling_numbers.split():
        assert number in r.json()["detail"]
    assert stub.calls == []


@pytest.mark.parametrize("value", [0, -1])
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (INTERPRET, {"query": "t"}),
        (RANK, rank_body("a", "b", "c")),
    ],
    ids=["max_terms", "max_scored"],
)
def test_non_positive_limit_is_422_before_calling_llm(make_stub_llm, path, body, value):
    field = "max_terms" if path == INTERPRET else "max_scored"
    stub = make_stub_llm({**TOPIC_ROUTES, **scored_all(3)})
    r = make_client(stub).post(path, json={**body, field: value})
    assert r.status_code == 422 and stub.calls == []


# --- LLM unavailable / error text never leaks ---


@pytest.mark.parametrize(
    ("path", "body"),
    [(INTERPRET, {"query": "q"}), (RANK, rank_body("a"))],
    ids=["interpret", "rank"],
)
def test_misconfigured_llm_is_503_with_fixed_detail(path, body):
    r = misconfigured_client().post(path, json=body)
    assert r.status_code == 503
    assert r.json()["detail"] == "LLM is not available or not configured"


def test_interpret_llm_error_is_503_without_provider_text(make_stub_llm):
    client = make_client(make_stub_llm({}, error=LLMError(f"bad key {SECRET}")))
    r = interpret(client)
    assert r.status_code == 503 and r.json()["detail"] == "LLM unavailable"
    assert SECRET not in r.text


def test_interpret_component_error_text_is_not_leaked(make_stub_llm):
    class FailingComponents:
        """Decompose succeeds; expansion and date parsing raise."""

        def __init__(self, inner):
            self.inner = inner

        async def generate(self, prompt, system=None, **kw):
            if EXPAND in (system or "") or DATE in (system or ""):
                raise LLMError(f"bad key {SECRET}")
            return await self.inner.generate(prompt, system=system, **kw)

    r = interpret(make_client(FailingComponents(make_stub_llm(FULL_ROUTES))))
    assert r.status_code == 200 and SECRET not in r.text
    assert "expansion failed" in r.json()["warnings"]
    assert "date parsing failed" in r.json()["warnings"]


# --- settings and capability advertisement ---


def test_discovery_enabled_requires_provider_and_key():
    assert discovery_enabled(Settings(llm_provider="openai", llm_api_key="k"))
    assert not discovery_enabled(Settings(llm_provider="openai"))
    assert not discovery_enabled(Settings(llm_api_key="k"))
    assert not discovery_enabled(Settings())


def test_conformance_class_only_when_enabled_and_survives_intersection_filter():
    assert discovery_conformance_classes(Settings()) == []
    enabled = Settings(llm_provider="openai", llm_api_key="k")
    assert discovery_conformance_classes(enabled) == [DISCOVERY_CONFORMANCE_CLASS]
    # core.conformance_classes intersects any class containing this with upstreams
    assert "collection-search" not in DISCOVERY_CONFORMANCE_CLASS


def test_discovery_links_are_post_links_under_base_url():
    links = discovery_links("http://localhost:8080/")
    assert {link["href"] for link in links} == {
        "http://localhost:8080/discovery/interpret",
        "http://localhost:8080/discovery/rank",
    }
    assert all(link["method"] == "POST" for link in links)


@pytest.mark.parametrize(
    "field", ["discovery_max_terms", "discovery_max_scored", "discovery_max_candidates"]
)
def test_discovery_ceiling_settings_must_be_positive(field):
    with pytest.raises(ValueError):
        Settings(**{field: 0})


@pytest.mark.parametrize(
    "old",
    ["max_expansion_terms", "rerank_candidate_count", "rerank_max_request_candidates"],
)
def test_old_limit_settings_are_removed(old):
    assert old not in Settings.model_fields
