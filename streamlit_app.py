"""Reference client for the LLM-assisted discovery flow.

Run the API first (with LLM_PROVIDER / LLM_API_KEY / GEOCODING_SERVICE_URL set):
    uv run uvicorn stac_fastapi.collection_discovery.app:app --port 8765

Then:
    uv run streamlit run streamlit_app.py

Flow: interpret -> one GET /collections per term (paging via `next` links) ->
merge and record matched terms -> rank -> display (paginated locally).
"""

from concurrent.futures import ThreadPoolExecutor

import httpx
import streamlit as st

MAX_RANK_CANDIDATES = 200  # server default discovery_max_candidates

st.set_page_config(page_title="STAC Collection Discovery", layout="wide")
st.title("Federated STAC Collection Discovery")

with st.sidebar:
    api_base = st.text_input("API base URL", "http://localhost:8765").rstrip("/")
    page_size = st.number_input("Per-request page size", 10, 1000, 100)
    max_pages = st.number_input("Max pages per term", 1, 20, 2)
    per_page = st.number_input("Results per display page", 5, 50, 10)
    max_terms = st.number_input("Max terms", min_value=1, value=10)
    max_scored = st.number_input("Max scored", min_value=1, value=50)
    apis_text = st.text_area("Upstream APIs (optional, one per line)", "")

query = st.text_input("Natural language query", "wildfires in California 2023")


def self_ref(collection: dict) -> str:
    """Source-qualified ref: the collection's own self link, else its id."""
    for link in collection.get("links", []):
        if link.get("rel") == "self":
            return link["href"]
    return collection["id"]


def fetch_term(term: str | None, plan: dict) -> list[dict]:
    params: dict = {"limit": page_size}
    if term is not None:
        params["q"] = term
    if plan["bbox"]:
        params["bbox"] = ",".join(str(c) for c in plan["bbox"])
    if plan["datetime"]:
        params["datetime"] = plan["datetime"]
    apis = [a.strip() for a in apis_text.splitlines() if a.strip()]
    if apis:
        params["apis"] = apis
    found, url = [], f"{api_base}/collections"
    for _ in range(int(max_pages)):
        r = httpx.get(url, params=params, timeout=60)
        r.raise_for_status()
        body = r.json()
        found.extend(body["collections"])
        nxt = next(
            (link["href"] for link in body.get("links", []) if link["rel"] == "next"),
            None,
        )
        if not nxt:
            break
        url, params = nxt, None  # next links carry all parameters
    return found


def run_search(nl_query: str) -> dict:
    r = httpx.post(
        f"{api_base}/discovery/interpret",
        json={"query": nl_query, "max_terms": int(max_terms)},
        timeout=60,
    )
    r.raise_for_status()
    plan = r.json()

    # No topic: one plain search without `q` (bbox/datetime only)
    terms = plan["q"] or [None]
    with ThreadPoolExecutor() as pool:
        per_term = list(pool.map(lambda t: fetch_term(t, plan), terms))

    merged: dict[str, dict] = {}
    for term, collections in zip(terms, per_term, strict=True):
        for c in collections:
            ref = self_ref(c)
            entry = merged.setdefault(ref, {"collection": c, "terms": []})
            if term is not None and term not in entry["terms"]:
                entry["terms"].append(term)

    candidates = sorted(merged.items(), key=lambda kv: -len(kv[1]["terms"]))
    candidates = candidates[:MAX_RANK_CANDIDATES]
    r = httpx.post(
        f"{api_base}/discovery/rank",
        json={
            "query": nl_query,
            "max_scored": int(max_scored),
            "candidates": [
                {
                    "ref": ref,
                    "id": e["collection"]["id"],
                    "title": e["collection"].get("title"),
                    "matched_terms": e["terms"],
                }
                for ref, e in candidates
            ],
        },
        timeout=120,
    )
    r.raise_for_status()
    ranking = r.json()
    return {
        "plan": plan,
        "warnings": plan["warnings"] + ranking["warnings"],
        "scored_count": ranking["scored_count"],
        "unscored_count": ranking["unscored_count"],
        "results": [
            {**merged[item["ref"]], "score": item["score"], "reason": item["reason"]}
            for item in ranking["ranked"]
        ],
    }


if st.button("Search", type="primary"):
    with st.spinner("Interpreting, searching and ranking..."):
        st.session_state["search"] = run_search(query)
        st.session_state["page"] = 1

search = st.session_state.get("search")
if not search:
    st.caption("Enter a query and press Search.")
    st.stop()

plan = search["plan"]
st.caption(
    f"q={plan['q']}  bbox={plan['bbox']}  datetime={plan['datetime']}  "
    f"scored={search['scored_count']}  unscored={search['unscored_count']}"
)
for warning in search["warnings"]:
    st.warning(warning)

results = search["results"]
pages = max(1, -(-len(results) // int(per_page)))
page = st.number_input("Page", 1, pages, key="page")
start = (int(page) - 1) * int(per_page)
for item in results[start : start + int(per_page)]:
    c = item["collection"]
    score = "unscored" if item["score"] is None else f"{item['score']:.1f}/10"
    st.subheader(f"{c.get('title') or c['id']}  ·  {score}")
    st.caption(f"{item['reason'] or ''}  |  matched: {', '.join(item['terms'])}")
    st.write((c.get("description") or "")[:400])
