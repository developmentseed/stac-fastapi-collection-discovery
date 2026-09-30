import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from stac_fastapi.collection_discovery.discovery import (
    build_discovery_router,
    get_llm,
)
from stac_fastapi.collection_discovery.llm.client import LLMError
from stac_fastapi.collection_discovery.settings import Settings

GEO = "https://geo.example"
DECOMPOSE = "extract structured fields"
EXPAND = "helping users find geospatial"
DATE = "date parsing assistant"
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


def make_client(stub=None, **settings_kwargs) -> TestClient:
    settings = Settings(llm_provider="openai", llm_api_key="test-key", **settings_kwargs)
    app = FastAPI()
    app.state.settings = settings
    app.include_router(build_discovery_router())
    if stub is not None:
        app.dependency_overrides[get_llm] = lambda: stub
    return TestClient(app)


@respx.mock
def test_interpret_full_query(make_stub_llm):
    respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=CALIFORNIA))
    client = make_client(make_stub_llm(FULL_ROUTES), geocoding_service_url=GEO)
    r = client.post(
        "/discovery/interpret", json={"query": "wildfires in California 2023"}
    )
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
    client = make_client(make_stub_llm(routes))
    body = client.post("/discovery/interpret", json={"query": "sst"}).json()
    assert body["q"] == ["sst", "sea surface temperature"]
    assert body["bbox"] is None and body["datetime"] is None and body["warnings"] == []


def test_interpret_geocoding_not_configured_warns_and_makes_no_request(make_stub_llm):
    with respx.mock(assert_all_called=False) as router:
        client = make_client(make_stub_llm(FULL_ROUTES))  # no geocoding_service_url
        body = client.post("/discovery/interpret", json={"query": "q"}).json()
        assert router.calls.call_count == 0
    assert body["bbox"] is None
    assert any("geocoding" in w for w in body["warnings"])
    assert body["datetime"] is not None  # other steps still succeed


@respx.mock
def test_interpret_malformed_geocoder_response_is_a_warning_not_500(make_stub_llm):
    respx.get(f"{GEO}/search").mock(
        return_value=httpx.Response(200, json=[{"display_name": "X"}])
    )
    client = make_client(make_stub_llm(FULL_ROUTES), geocoding_service_url=GEO)
    r = client.post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 200
    assert r.json()["bbox"] is None
    assert any("California" in w for w in r.json()["warnings"])


def test_interpret_date_parse_failure_is_a_warning(make_stub_llm):
    routes = {**FULL_ROUTES, DATE: {"error": "cannot parse"}}
    client = make_client(make_stub_llm(routes))
    body = client.post("/discovery/interpret", json={"query": "q"}).json()
    assert body["datetime"] is None
    assert any("date" in w for w in body["warnings"])


def test_interpret_unparseable_expansion_keeps_topic_only(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "wildfires", "location": None, "date_expression": None},
        EXPAND: "not json",
    }
    client = make_client(make_stub_llm(routes))
    body = client.post("/discovery/interpret", json={"query": "wildfires"}).json()
    assert body["q"] == ["wildfires"]


def test_interpret_respects_max_expansion_terms(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "t", "location": None, "date_expression": None},
        EXPAND: ["a", "b", "c", "d"],
    }
    client = make_client(make_stub_llm(routes), max_expansion_terms=2)
    assert client.post("/discovery/interpret", json={"query": "t"}).json()["q"] == [
        "t",
        "a",
        "b",
    ]


def test_interpret_llm_error_is_503(make_stub_llm):
    client = make_client(make_stub_llm({}, error=LLMError("down")))
    r = client.post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 503 and "LLM" in r.json()["detail"]


def test_interpret_llm_misconfigured_is_503():
    app = FastAPI()
    app.state.settings = Settings()  # no provider/key
    app.include_router(build_discovery_router())
    r = TestClient(app).post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 503


@pytest.mark.parametrize("query", ["", "   ", "x" * 1001])
def test_interpret_rejects_blank_or_overlong_query_before_calling_llm(
    make_stub_llm, query
):
    stub = make_stub_llm(FULL_ROUTES)
    r = make_client(stub).post("/discovery/interpret", json={"query": query})
    assert r.status_code == 422 and stub.calls == []


def test_interpret_rejects_unknown_fields(make_stub_llm):
    r = make_client(make_stub_llm(FULL_ROUTES)).post(
        "/discovery/interpret", json={"query": "q", "extra": 1}
    )
    assert r.status_code == 422


@respx.mock
def test_interpret_geocoder_result_with_non_dict_geojson_is_a_warning(make_stub_llm):
    bad = [
        {
            "boundingbox": ["1", "2", "3", "4"],
            "display_name": "X",
            "geojson": "a string",
        }
    ]
    respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=bad))
    client = make_client(make_stub_llm(FULL_ROUTES), geocoding_service_url=GEO)
    r = client.post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 200
    assert r.json()["bbox"] is None
    assert any("California" in w for w in r.json()["warnings"])


@pytest.mark.parametrize("date_reply", [[1, 2], {"start": 2023, "end": 2024}])
def test_interpret_malformed_date_output_is_a_warning_not_500(make_stub_llm, date_reply):
    routes = {**FULL_ROUTES, DATE: date_reply}
    r = make_client(make_stub_llm(routes)).post(
        "/discovery/interpret", json={"query": "q"}
    )
    assert r.status_code == 200
    assert r.json()["datetime"] is None
    assert any("date" in w for w in r.json()["warnings"])


RERANK = "ranking geospatial"


def rank_body(*ids, **extra):
    return {"query": "wildfires", "candidates": [{"id": i} for i in ids], **extra}


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
    r = make_client(stub).post("/discovery/rank", json=body)
    assert r.status_code == 200
    assert r.json() == {
        "ranked": [
            {"ref": "y", "score": 9.0, "reason": "strong"},
            {"ref": "https://a/collections/x", "score": 3.0, "reason": "weak"},
        ],
        "unscored_count": 0,
        "warnings": [],
    }


def test_rank_presorts_by_matched_terms_and_reports_unscored(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": [{"i": 1, "score": 8, "reason": "ok"}]}})
    body = {
        "query": "q",
        "candidates": [{"id": "a"}, {"id": "b", "matched_terms": ["t1", "t2"]}],
    }
    r = make_client(stub, rerank_candidate_count=1).post("/discovery/rank", json=body)
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
    r = make_client(stub).post("/discovery/rank", json=body)
    assert r.status_code == 422 and "same" in r.text and stub.calls == []


def test_rank_distinct_refs_allow_same_id(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": []}})
    body = {
        "query": "q",
        "candidates": [{"id": "same", "ref": "a|same"}, {"id": "same", "ref": "b|same"}],
    }
    assert make_client(stub).post("/discovery/rank", json=body).status_code == 200


def test_rank_over_request_limit_is_422(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": []}})
    r = make_client(stub, rerank_max_request_candidates=2).post(
        "/discovery/rank", json=rank_body("a", "b", "c")
    )
    assert r.status_code == 422 and stub.calls == []


def test_rank_rejects_full_collection_objects(make_stub_llm):
    body = {
        "query": "q",
        "candidates": [{"id": "a", "title": "A", "extent": {"spatial": {}}, "links": []}],
    }
    r = make_client(make_stub_llm({RERANK: {"ranked": []}})).post(
        "/discovery/rank", json=body
    )
    assert r.status_code == 422


def test_rank_empty_candidates_is_200_and_makes_no_llm_call(make_stub_llm):
    stub = make_stub_llm({})
    r = make_client(stub).post("/discovery/rank", json={"query": "q", "candidates": []})
    assert r.status_code == 200
    assert r.json() == {"ranked": [], "unscored_count": 0, "warnings": []}
    assert stub.calls == []


def test_rank_llm_failure_returns_200_unscored_with_warning(make_stub_llm):
    stub = make_stub_llm({}, error=LLMError("down"))
    r = make_client(stub).post("/discovery/rank", json=rank_body("a", "b"))
    assert r.status_code == 200
    assert [x["score"] for x in r.json()["ranked"]] == [None, None]
    assert r.json()["unscored_count"] == 2
    assert r.json()["warnings"] == ["rerank: LLM error: down"]


def test_rank_llm_misconfigured_is_503():
    app = FastAPI()
    app.state.settings = Settings()
    app.include_router(build_discovery_router())
    assert TestClient(app).post("/discovery/rank", json=rank_body("a")).status_code == 503


@pytest.mark.parametrize("query", ["", "   ", "x" * 1001])
def test_rank_rejects_blank_or_overlong_query(make_stub_llm, query):
    r = make_client(make_stub_llm({})).post(
        "/discovery/rank", json={"query": query, "candidates": [{"id": "a"}]}
    )
    assert r.status_code == 422


from stac_fastapi.collection_discovery.discovery import (  # noqa: E402
    DISCOVERY_CONFORMANCE_CLASS,
    discovery_conformance_classes,
    discovery_enabled,
    discovery_links,
)


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
    "fields",
    [
        {"topic": ["fire"], "location": None, "date_expression": None},
        {"topic": 42, "location": None, "date_expression": None},
        {"topic": "fire", "location": ["California"], "date_expression": None},
        {"topic": "fire", "location": 7, "date_expression": None},
        {"topic": "fire", "location": None, "date_expression": ["2023"]},
        {"topic": "fire", "location": None, "date_expression": 2023},
    ],
)
def test_interpret_non_string_decomposer_fields_never_500(make_stub_llm, fields):
    routes = {DECOMPOSE: fields, EXPAND: ["burned area"], DATE: {"error": "x"}}
    r = make_client(make_stub_llm(routes)).post(
        "/discovery/interpret", json={"query": "q"}
    )
    assert r.status_code == 200
    assert all(isinstance(t, str) for t in r.json()["q"])


def test_interpret_without_topic_returns_empty_q_but_resolves_bbox_and_datetime(
    make_stub_llm,
):
    routes = {
        DECOMPOSE: {"topic": None, "location": "California", "date_expression": "2023"},
        DATE: {"start": "2023-01-01", "end": "2023-12-31"},
    }
    stub = make_stub_llm(routes)
    with respx.mock:
        respx.get(f"{GEO}/search").mock(return_value=httpx.Response(200, json=CALIFORNIA))
        client = make_client(stub, geocoding_service_url=GEO)
        r = client.post("/discovery/interpret", json={"query": "California 2023"})
    body = r.json()
    assert r.status_code == 200
    assert body["q"] == []
    assert body["bbox"] == [-124.4, 32.5, -114.1, 42.0]
    assert body["datetime"] is not None
    assert any("no topic" in w for w in body["warnings"])
    assert not any(EXPAND in (c["system"] or "") for c in stub.calls)


def test_interpret_blank_topic_is_treated_as_no_topic(make_stub_llm):
    routes = {DECOMPOSE: {"topic": "   ", "location": None, "date_expression": None}}
    r = make_client(make_stub_llm(routes)).post(
        "/discovery/interpret", json={"query": "q"}
    )
    assert r.json()["q"] == [] and any("no topic" in w for w in r.json()["warnings"])
