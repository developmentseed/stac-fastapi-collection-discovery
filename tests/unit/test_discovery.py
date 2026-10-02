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
    assert "date parsing failed" in body["warnings"]
    assert "cannot parse" not in str(body)


def test_interpret_unparseable_expansion_keeps_topic_only(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "wildfires", "location": None, "date_expression": None},
        EXPAND: "not json",
    }
    client = make_client(make_stub_llm(routes))
    body = client.post("/discovery/interpret", json={"query": "wildfires"}).json()
    assert body["q"] == ["wildfires"]
    assert any("expansion" in w for w in body["warnings"])


def test_interpret_respects_max_terms(make_stub_llm):
    routes = {
        DECOMPOSE: {"topic": "t", "location": None, "date_expression": None},
        EXPAND: ["a", "b", "c", "d"],
    }
    client = make_client(make_stub_llm(routes))
    r = client.post("/discovery/interpret", json={"query": "t", "max_terms": 3})
    assert r.json()["q"] == ["t", "a", "b"]


def test_interpret_llm_error_is_503(make_stub_llm):
    client = make_client(make_stub_llm({}, error=LLMError("down")))
    r = client.post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 503 and r.json()["detail"] == "LLM unavailable"


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
        "scored_count": 2,
        "unscored_count": 0,
        "warnings": [],
    }


def test_rank_presorts_by_matched_terms_and_reports_unscored(make_stub_llm):
    stub = make_stub_llm({RERANK: {"ranked": [{"i": 1, "score": 8, "reason": "ok"}]}})
    body = {
        "query": "q",
        "candidates": [{"id": "a"}, {"id": "b", "matched_terms": ["t1", "t2"]}],
    }
    r = make_client(stub).post("/discovery/rank", json={**body, "max_scored": 1})
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
    r = make_client(stub, discovery_max_candidates=2).post(
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
    assert r.json() == {
        "ranked": [],
        "scored_count": 0,
        "unscored_count": 0,
        "warnings": [],
    }
    assert stub.calls == []


def test_rank_llm_failure_returns_200_unscored_with_warning(make_stub_llm):
    stub = make_stub_llm({}, error=LLMError("down"))
    r = make_client(stub).post("/discovery/rank", json=rank_body("a", "b"))
    assert r.status_code == 200
    assert [x["score"] for x in r.json()["ranked"]] == [None, None]
    assert r.json()["unscored_count"] == 2
    assert r.json()["warnings"] == ["rerank: LLM call failed"]


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


def test_rank_non_json_reply_is_200_unscored_with_rerank_warning(make_stub_llm):
    stub = make_stub_llm({RERANK: "not json"})
    r = make_client(stub).post("/discovery/rank", json=rank_body("a", "b"))
    assert r.status_code == 200
    assert [x["score"] for x in r.json()["ranked"]] == [None, None]
    assert r.json()["unscored_count"] == 2
    assert any(w.startswith("rerank:") for w in r.json()["warnings"])


SECRET = "sk-secret"


def test_interpret_decompose_error_text_is_not_leaked(make_stub_llm):
    client = make_client(make_stub_llm({}, error=LLMError(f"bad key {SECRET}")))
    r = client.post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 503 and SECRET not in r.text


def test_interpret_component_error_text_is_not_leaked(make_stub_llm):
    class Stub:
        def __init__(self, inner):
            self.inner = inner

        async def generate(self, prompt, system=None, **kw):
            if EXPAND in (system or "") or DATE in (system or ""):
                raise LLMError(f"bad key {SECRET}")
            return await self.inner.generate(prompt, system=system, **kw)

    inner = make_stub_llm(FULL_ROUTES)
    r = make_client(Stub(inner)).post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 200 and SECRET not in r.text
    assert "expansion failed" in r.json()["warnings"]
    assert "date parsing failed" in r.json()["warnings"]


def test_rank_error_text_is_not_leaked(make_stub_llm):
    stub = make_stub_llm({}, error=LLMError(f"bad key {SECRET}"))
    r = make_client(stub).post("/discovery/rank", json=rank_body("a"))
    assert r.status_code == 200 and SECRET not in r.text
    assert r.json()["warnings"] == ["rerank: LLM call failed"]


def test_rank_no_usable_scores_warning_is_fixed_text(make_stub_llm):
    r = make_client(make_stub_llm({RERANK: "not json"})).post(
        "/discovery/rank", json=rank_body("a")
    )
    assert r.json()["warnings"] == ["rerank: LLM returned no usable scores"]


def test_misconfigured_llm_detail_is_fixed_text():
    app = FastAPI()
    app.state.settings = Settings()
    app.include_router(build_discovery_router())
    r = TestClient(app).post("/discovery/interpret", json={"query": "q"})
    assert r.status_code == 503
    assert r.json()["detail"] == "LLM is not available or not configured"


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


# --- client-chosen limits ---

TOPIC_ROUTES = {
    DECOMPOSE: {"topic": "t", "location": None, "date_expression": None},
    EXPAND: [f"e{i}" for i in range(20)],
}


def test_interpret_default_max_terms_is_10(make_stub_llm):
    r = make_client(make_stub_llm(TOPIC_ROUTES)).post(
        "/discovery/interpret", json={"query": "t"}
    )
    assert len(r.json()["q"]) == 10 and r.json()["q"][0] == "t"


def test_interpret_null_max_terms_uses_default(make_stub_llm):
    r = make_client(make_stub_llm(TOPIC_ROUTES)).post(
        "/discovery/interpret", json={"query": "t", "max_terms": None}
    )
    assert len(r.json()["q"]) == 10


def test_interpret_max_terms_above_ceiling_is_422(make_stub_llm):
    stub = make_stub_llm(TOPIC_ROUTES)
    r = make_client(stub, discovery_max_terms=25).post(
        "/discovery/interpret", json={"query": "t", "max_terms": 40}
    )
    assert r.status_code == 422
    assert "40" in r.json()["detail"] and "25" in r.json()["detail"]
    assert stub.calls == []


def test_interpret_max_terms_at_ceiling_is_ok(make_stub_llm):
    r = make_client(make_stub_llm(TOPIC_ROUTES), discovery_max_terms=15).post(
        "/discovery/interpret", json={"query": "t", "max_terms": 15}
    )
    assert r.status_code == 200 and len(r.json()["q"]) == 15


@pytest.mark.parametrize("value", [0, -1])
def test_interpret_max_terms_must_be_positive(make_stub_llm, value):
    stub = make_stub_llm(TOPIC_ROUTES)
    r = make_client(stub).post(
        "/discovery/interpret", json={"query": "t", "max_terms": value}
    )
    assert r.status_code == 422 and stub.calls == []


def test_interpret_max_terms_1_skips_expansion_call(make_stub_llm):
    stub = make_stub_llm(TOPIC_ROUTES)
    r = make_client(stub).post(
        "/discovery/interpret", json={"query": "t", "max_terms": 1}
    )
    assert r.status_code == 200 and r.json()["q"] == ["t"]
    assert r.json()["warnings"] == []
    assert len(stub.calls) == 1 and DECOMPOSE in stub.calls[0]["system"]


def test_interpret_default_clamped_to_lower_ceiling(make_stub_llm):
    r = make_client(make_stub_llm(TOPIC_ROUTES), discovery_max_terms=4).post(
        "/discovery/interpret", json={"query": "t"}
    )
    assert r.status_code == 200 and len(r.json()["q"]) == 4


def test_interpret_no_topic_with_max_terms_is_empty_q(make_stub_llm):
    routes = {DECOMPOSE: {"topic": "", "location": None, "date_expression": None}}
    r = make_client(make_stub_llm(routes)).post(
        "/discovery/interpret", json={"query": "q", "max_terms": 1}
    )
    assert r.status_code == 200 and r.json()["q"] == []


def many(n):
    return [{"id": f"c{i}"} for i in range(n)]


def scored_all(n):
    return {
        RERANK: {"ranked": [{"i": i + 1, "score": 5, "reason": "r"} for i in range(n)]}
    }


def test_rank_default_max_scored_is_50(make_stub_llm):
    stub = make_stub_llm(scored_all(50))
    body = {"query": "q", "candidates": many(80)}
    r = make_client(stub, discovery_max_scored=100).post("/discovery/rank", json=body)
    assert r.status_code == 200
    assert r.json()["scored_count"] == 50 and r.json()["unscored_count"] == 30
    assert "50. " in stub.calls[0]["prompt"] and "51. " not in stub.calls[0]["prompt"]


def test_rank_max_scored_takes_effect(make_stub_llm):
    stub = make_stub_llm(scored_all(2))
    body = {"query": "q", "candidates": many(5), "max_scored": 2}
    r = make_client(stub).post("/discovery/rank", json=body)
    assert r.json()["scored_count"] == 2 and r.json()["unscored_count"] == 3
    assert "2. " in stub.calls[0]["prompt"] and "3. " not in stub.calls[0]["prompt"]


def test_rank_null_max_scored_uses_default(make_stub_llm):
    stub = make_stub_llm(scored_all(50))
    body = {"query": "q", "candidates": many(60), "max_scored": None}
    assert (
        make_client(stub).post("/discovery/rank", json=body).json()["scored_count"] == 50
    )


def test_rank_max_scored_above_ceiling_is_422(make_stub_llm):
    stub = make_stub_llm(scored_all(5))
    body = {"query": "q", "candidates": many(5), "max_scored": 30}
    r = make_client(stub, discovery_max_scored=20).post("/discovery/rank", json=body)
    assert r.status_code == 422
    assert "30" in r.json()["detail"] and "20" in r.json()["detail"]
    assert stub.calls == []


@pytest.mark.parametrize("value", [0, -3])
def test_rank_max_scored_must_be_positive(make_stub_llm, value):
    stub = make_stub_llm(scored_all(5))
    body = {"query": "q", "candidates": many(5), "max_scored": value}
    assert make_client(stub).post("/discovery/rank", json=body).status_code == 422
    assert stub.calls == []


def test_rank_max_scored_larger_than_candidates_scores_all(make_stub_llm):
    stub = make_stub_llm(scored_all(3))
    body = {"query": "q", "candidates": many(3), "max_scored": 90}
    j = make_client(stub).post("/discovery/rank", json=body).json()
    assert j["scored_count"] == 3 and j["unscored_count"] == 0


def test_rank_default_clamped_to_lower_ceiling(make_stub_llm):
    stub = make_stub_llm(scored_all(20))
    body = {"query": "q", "candidates": many(30)}
    r = make_client(stub, discovery_max_scored=20).post("/discovery/rank", json=body)
    assert r.status_code == 200
    assert r.json()["scored_count"] == 20
    assert r.json()["scored_count"] + r.json()["unscored_count"] == 30


def test_rank_duplicate_refs_detail_is_bounded(make_stub_llm):
    ids = [f"dup{i}-" + "x" * 200 for i in range(8)]
    body = {"query": "q", "candidates": [{"id": i} for i in ids for _ in range(2)]}
    r = make_client(make_stub_llm({RERANK: {"ranked": []}})).post(
        "/discovery/rank", json=body
    )
    detail = r.json()["detail"]
    assert r.status_code == 422
    assert "8" in detail
    assert "dup0-" in detail and "dup1-" not in detail  # first (sorted) example only
    assert "x" * 101 not in detail
    assert len(detail) < 300
