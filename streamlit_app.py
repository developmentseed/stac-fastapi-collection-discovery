"""Demo UI for the LLM-assisted collection search endpoint.

Run the API first:
    uv run uvicorn stac_fastapi.collection_discovery.app:app --port 8765

Then:
    uv run streamlit run streamlit_app.py
"""

import httpx
import streamlit as st

st.set_page_config(page_title="STAC Collection Discovery", layout="wide")
st.title("Federated STAC Collection Discovery")

with st.sidebar:
    st.header("Settings")
    api_base = st.text_input("API base URL", "http://localhost:8765")
    limit = st.number_input("Results limit", min_value=1, max_value=50, value=10)
    apis_text = st.text_area(
        "Upstream APIs (optional, one per line)",
        "",
        help="Leave blank to use the server's configured upstream APIs.",
    )

query = st.text_input(
    "Natural language query",
    "wildfires in California 2023",
    placeholder="e.g. sea surface temperature in the Gulf of Mexico since 2020",
)
search = st.button("Search", type="primary")

if not (search or st.session_state.get("response")):
    st.caption(
        "Enter a query — the API decomposes it with an LLM, expands the topic, "
        "federates across upstream catalogs, and re-ranks by relevance."
    )
    st.stop()

if search:
    params: dict = {"query": query, "limit": limit}
    apis = [a.strip() for a in apis_text.splitlines() if a.strip()]
    with st.spinner("Running assisted search (LLM + federated catalogs)..."):
        try:
            r = httpx.get(
                f"{api_base}/collections",
                params=[("apis", a) for a in apis] + list(params.items()),
                timeout=120,
            )
            r.raise_for_status()
            st.session_state["response"] = r.json()
        except httpx.HTTPStatusError as e:
            st.session_state["response"] = None
            st.error(f"API error {e.response.status_code}: {e.response.text}")
        except httpx.HTTPError as e:
            st.session_state["response"] = None
            st.error(f"Request failed: {e}")

data = st.session_state.get("response")
if not data:
    st.stop()

# --- Pipeline trace ---
meta = data.get("search_metadata") or {}
if meta:
    place = meta.get("resolved_place") or meta.get("location") or "—"
    st.caption(
        f"**{meta.get('topic') or '—'}** · {place} · "
        f"{meta.get('datetime_range') or '—'} · "
        f"{meta.get('total_time_ms', 0) / 1000:.1f}s · "
        f"{meta.get('candidate_count', 0)} candidates -> "
        f"{len(data.get('collections') or [])} ranked"
    )

    terms = meta.get("expanded_terms") or []
    if terms:
        st.caption("expanded: " + " · ".join(f"`{t}`" for t in terms))

    counts = meta.get("per_api_counts") or {}
    if counts:
        st.caption(
            "per-API: "
            + " · ".join(f"{api.split('/')[2]}: {n}" for api, n in counts.items())
        )

    for err in meta.get("errors") or []:
        st.warning(err)

# --- Results ---
collections = data.get("collections") or []
st.subheader(f"Ranked results ({len(collections)})")

for i, coll in enumerate(collections, 1):
    info = coll.get("assisted_search") or {}
    title = coll.get("title") or coll.get("id", "(untitled)")
    score = info.get("score")
    label = f"{i}. {title}"
    if score is not None:
        label += f"  —  score {score}/10"

    with st.expander(label, expanded=i <= 3):
        if info.get("reason"):
            st.write(info["reason"])
        st.caption(
            f"source: {info.get('source_api', '—')} · "
            f"matched term: `{info.get('matched_term', '—')}`"
        )
        st.json(coll, expanded=False)
