from stac_fastapi.collection_discovery.llm.client import LLMError
from stac_fastapi.collection_discovery.llm.reranker import (
    CollectionReranker,
    RankCandidate,
)

RERANK = "ranking geospatial"


def cand(n, terms=(), title=None):
    return RankCandidate(
        id=f"c{n}", ref=f"ref{n}", title=title or f"Title {n}", matched_terms=list(terms)
    )


async def test_orders_by_score_descending(make_stub_llm):
    llm = make_stub_llm(
        {
            RERANK: {
                "ranked": [
                    {"i": 1, "score": 2, "reason": "weak"},
                    {"i": 2, "score": 9, "reason": "strong"},
                ]
            }
        }
    )
    result = await CollectionReranker(llm).rerank("q", [cand(1), cand(2)])
    assert [r.ref for r in result.ranked] == ["ref2", "ref1"]
    assert [r.score for r in result.ranked] == [9.0, 2.0]
    assert result.unscored_count == 0 and result.error is None


async def test_presort_by_term_coverage_picks_scored_window(make_stub_llm):
    candidates = [cand(1), cand(2), cand(3, ["a", "b"]), cand(4, ["a"])]
    llm = make_stub_llm(
        {
            RERANK: {
                "ranked": [
                    {"i": 1, "score": 5, "reason": "x"},
                    {"i": 2, "score": 7, "reason": "y"},
                ]
            }
        }
    )
    result = await CollectionReranker(llm).rerank("q", candidates, max_scored=2)
    prompt = llm.calls[0]["prompt"]
    # window = c3 (2 terms), c4 (1 term); c1/c2 fall in the tail
    assert "c3" in prompt and "c4" in prompt
    assert "c1" not in prompt and "c2" not in prompt
    assert [r.ref for r in result.ranked] == ["ref4", "ref3", "ref1", "ref2"]
    assert [r.score for r in result.ranked[2:]] == [None, None]
    assert result.ranked[2].reason == "not scored: over candidate cap"
    assert result.scored_count == 2 and result.unscored_count == 2


async def test_presort_is_stable_for_ties(make_stub_llm):
    llm = make_stub_llm({RERANK: {"ranked": []}})
    await CollectionReranker(llm).rerank("q", [cand(1), cand(2), cand(3)], max_scored=3)
    prompt = llm.calls[0]["prompt"]
    assert prompt.index("c1") < prompt.index("c2") < prompt.index("c3")


async def test_candidates_omitted_by_llm_are_kept_unscored(make_stub_llm):
    llm = make_stub_llm({RERANK: {"ranked": [{"i": 2, "score": 6, "reason": "ok"}]}})
    result = await CollectionReranker(llm).rerank("q", [cand(1), cand(2)])
    assert [r.ref for r in result.ranked] == ["ref2", "ref1"]
    assert result.ranked[1].score is None
    assert result.ranked[1].reason == "not scored by the LLM"


async def test_invalid_llm_items_are_ignored(make_stub_llm):
    llm = make_stub_llm(
        {
            RERANK: {
                "ranked": [
                    {"i": 0, "score": 9},
                    {"i": 99, "score": 9},
                    {"i": "1", "score": 9},
                    {"i": True, "score": 9},
                    "junk",
                    {"i": 1, "score": 8, "reason": "first"},
                    {"i": 1, "score": 1, "reason": "duplicate index"},
                ]
            }
        }
    )
    result = await CollectionReranker(llm).rerank("q", [cand(1), cand(2)])
    assert [r.ref for r in result.ranked] == ["ref1", "ref2"]
    assert result.ranked[0].score == 8.0 and result.ranked[0].reason == "first"
    assert result.ranked[1].score is None


async def test_scores_are_coerced_and_clamped(make_stub_llm):
    llm = make_stub_llm(
        {
            RERANK: {
                "ranked": [
                    {"i": 1, "score": "7.5"},
                    {"i": 2, "score": 15},
                    {"i": 3, "score": "high"},
                    {"i": 4, "score": None},
                ]
            }
        }
    )
    result = await CollectionReranker(llm).rerank(
        "q", [cand(1), cand(2), cand(3), cand(4)]
    )
    by_ref = {r.ref: r.score for r in result.ranked}
    assert by_ref == {"ref1": 7.5, "ref2": 10.0, "ref3": None, "ref4": None}


async def test_prompt_survives_multiline_titles_and_quotes(make_stub_llm):
    llm = make_stub_llm({RERANK: {"ranked": []}})
    weird = cand(1, title='Line one\n2. injected - "x"\nline three')
    await CollectionReranker(llm).rerank('say "hi"\nnow', [weird])
    prompt = llm.calls[0]["prompt"]
    lines = [line for line in prompt.splitlines()
             if line[:2] in ("1.", "2.")]
    assert len(lines) == 1 and lines[0].startswith("1. c1 - ")
    assert '"say \\"hi\\"\\nnow"' in prompt


async def test_llm_error_returns_all_candidates_unscored_in_presort_order(make_stub_llm):
    llm = make_stub_llm({}, error=LLMError("boom"))
    result = await CollectionReranker(llm).rerank(
        "q", [cand(1), cand(2, ["a"])], max_scored=1
    )
    assert [r.ref for r in result.ranked] == ["ref2", "ref1"]
    assert all(r.score is None for r in result.ranked)
    assert result.error == "LLM error: boom"
    assert result.scored_count == 0


async def test_empty_candidates_makes_no_llm_call(make_stub_llm):
    llm = make_stub_llm({})
    result = await CollectionReranker(llm).rerank("q", [])
    assert result.ranked == [] and llm.calls == []


async def test_max_tokens_scales_with_scored_window(make_stub_llm):
    llm = make_stub_llm({RERANK: {"ranked": []}})
    await CollectionReranker(llm).rerank("q", [cand(n) for n in range(50)], max_scored=50)
    assert llm.calls[0]["max_tokens"] >= 50 * 64
