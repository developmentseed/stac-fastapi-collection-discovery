# Vision

Status: draft
Type: exploratory
Owner: Development Seed Federated Search Team
Date: 2026-10-02

## What this project is

  Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. This project exists to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more often than this API's own federated keyword search over the same catalogs, so a win is credited to the LLM and nothing else. If it does not, we stop; if it does, we decide whether to run it as a service.

  The product is the API. Its natural-language search is reached through the `query` parameter; plain STAC clients still work against it but get keyword search. The experiment runs through the Streamlit demo, kept to a query box, the ranked list and each match's reason, so what is judged is the API's ranking. The reason for each match is extra, and the result must stand without it.

❓ [scope Q5] Where does the keyword side of the test run?: Line 10 compares the natural-language search with this API's federated keyword search over the same catalogs. This line says the experiment runs through the Streamlit demo, but the demo sends only `query` (streamlit_app.py line 41), so a scientist there never sees the keyword side. Is the keyword side part of the demo the scientists use, or is it judged somewhere else, such as STAC Browser pointed at this API?

➡️ The demo runs both searches over the same catalogs, so the scientist judges both in the same place and the same way.

❓ [scope Q4] Does keyword search stop if the LLM loses?: This line makes the API the product, and plain STAC clients get its federated keyword search. That keyword mode is most of the code and the whole README "Features" list. Line 10 says "if it does not, we stop". If the LLM does not win, does the federated keyword search stop too, or does it go on as a product of its own?

➡️ If the LLM does not win, the whole project stops, keyword search included. Federated keyword search is here only as the baseline and as what plain STAC clients get.

❓ [critique C4] The reason is shown, so is it judged?: The demo shows each match's reason to the scientist, and this line says the result must stand without it. A well-written reason can make a weak match look right, so the scientist may be judging the LLM's wording, not the API's ranking. Which holds: the reason is part of what is being tested, or the experiment must show that the ranking wins without it?

➡️ The reason is part of what we test: a scientist picks a collection partly because the reason explains it. We do not claim the ranking alone wins.

## Who it is for
Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords. Our user wants data, not catalogs; that the search spans several catalogs is our concern, not theirs.

❓ [critique Q9] Is a collection enough for someone who wants data?: This line says the user wants data. The non-goals stop at the collection and hand the user to the upstream API for items. A tempting proposal: "add item search, since the user wants data". Is reaching the right collection the whole job for this user, or only the first step, with getting the data left to them on purpose?

➡️ Reaching the right collection is the whole job. Once the user has it, the upstream catalog's own tools get them the data, and we do not try to do that better.

## Goals
Scientists reach the right collection(s)

❓ [critique Q8] Reach it, or reach it more often?: Line 10 says success means reaching the right collection more often than with this API's federated keyword search. This goal only says "reach", and keyword search may already do that for many queries. Is the goal the comparison from line 10, or something else?

➡️ Scientists reach the right collection more often with the natural-language search than with this API's federated keyword search over the same catalogs.


## Non-goals

Data analysis, data visualization. Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs.

❓ [critique Q10] Is running it as a service out for now?: Line 10 says we decide whether to run it as a service only if the experiment wins. Nothing here rules out work for a service before then: uptime, scale, cost limits, support for outside users. Is that work out until the experiment is decided?

➡️ Running this as a supported service is out until the experiment shows a win. Until then we build only what the experiment needs.

## Constraints

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs.

## Direction

Currently, the focus is getting users to the correct dataset across multiple STAC catalogs from a plain-language request like
  ▎ "wildfires in 2023", even when the catalogs never use those words.

❓ [critique C5] Can it find words the catalogs never use, with no index?: With no index, candidates come only from the upstream keyword search. In pipeline.py the LLM expands the topic into terms (step 4), each term goes to upstream keyword search (step 5), and the re-ranker sees only what that returns (step 6). So a collection is found only if the LLM guesses a word the catalog does use. Does the direction accept that limit, or would a miss here be the reason to drop the no-index non-goal?

➡️ We accept the limit: the search finds a collection only when the LLM's terms match words the catalog uses. If that misses too often, we stop; we do not add an index.
