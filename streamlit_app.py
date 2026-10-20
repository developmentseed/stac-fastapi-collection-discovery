"""Reference client for the LLM-assisted discovery flow.

Run the API first (with LLM_PROVIDER / LLM_API_KEY / GEOCODING_SERVICE_URL set):
    uv run uvicorn stac_fastapi.collection_discovery.app:app --port 8765

Then:
    uv run streamlit run streamlit_app.py

Flow: interpret -> search (one federated search per term, merged with matched
terms) -> rank -> display (paginated locally).
"""

import httpx
import streamlit as st

st.set_page_config(page_title="STAC Collection Discovery", layout="wide")
st.title("Federated STAC Collection Discovery")

with st.sidebar:
    api_base = st.text_input("API base URL", "http://localhost:8765").rstrip("/")
    page_size = st.number_input("Per-request page size", 10, 1000, 100)
    max_pages = st.number_input("Max pages per term", 1, 5, 2)
    per_page = st.number_input("Results per display page", 5, 50, 10)
    max_terms = st.number_input("Max terms", min_value=1, value=10)
    max_scored = st.number_input("Max scored", min_value=1, value=50)
    apis_text = st.text_area("Upstream APIs (optional, one per line)", "")

query = st.text_input("Natural language query", "wildfires in California 2023")


def run_search(nl_query: str) -> dict:
    r = httpx.post(
        f"{api_base}/discovery/interpret",
        json={"query": nl_query, "max_terms": int(max_terms)},
        timeout=60,
    )
    r.raise_for_status()
    plan = r.json()

    apis = [a.strip() for a in apis_text.splitlines() if a.strip()]
    r = httpx.post(
        f"{api_base}/discovery/search",
        json={
            "q": plan["q"],
            "bbox": plan["bbox"],
            "datetime": plan["datetime"],
            "limit": int(page_size),
            "max_pages": int(max_pages),
            "include_collections": True,
            **({"apis": apis} if apis else {}),
        },
        timeout=120,
    )
    r.raise_for_status()
    found = r.json()

    r = httpx.post(
        f"{api_base}/discovery/rank",
        json={
            "query": nl_query,
            "max_scored": int(max_scored),
            "candidates": found["candidates"],
        },
        timeout=120,
    )
    r.raise_for_status()
    ranking = r.json()
    terms = {c["ref"]: c["matched_terms"] for c in found["candidates"]}
    failed = [f"{f['api']} failed for {f['term']!r}" for f in found["failed"]]
    return {
        "plan": plan,
        "warnings": plan["warnings"] + found["warnings"] + failed + ranking["warnings"],
        "scored_count": ranking["scored_count"],
        "unscored_count": ranking["unscored_count"],
        "results": [
            {
                "collection": found["collections"][item["ref"]],
                "terms": terms[item["ref"]],
                "score": item["score"],
                "reason": item["reason"],
            }
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
if not results:
    st.info(
        "No collections found. Every term returned nothing from the upstream APIs "
        "with these filters; try a broader query or different upstream APIs."
    )
    st.stop()

pages = max(1, -(-len(results) // int(per_page)))
page = st.number_input("Results page", 1, pages, key="page")
start = (int(page) - 1) * int(per_page)
end = min(start + int(per_page), len(results))
st.caption(f"Showing {start + 1}–{end} of {len(results)} (page {int(page)} of {pages})")
for item in results[start:end]:
    c = item["collection"]
    score = "unscored" if item["score"] is None else f"{item['score']:.1f}/10"
    st.subheader(f"{c.get('title') or c['id']}  ·  {score}")
    st.caption(f"{item['reason'] or ''}  |  matched: {', '.join(item['terms'])}")
    st.write((c.get("description") or "")[:400])
