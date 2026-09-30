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
