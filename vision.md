# Vision

<!--
Write this by hand. A page at most. Every later question and review points
back here. Numbers, names, paths and procedures belong in conops.md, not
here. The personas write their questions into this file, each under the line
it is about; answer one by rewriting that line in your own words and deleting
the block. Delete these comments when done.
-->

Status: draft
Type: exploratory
Owner: Development Seed Federated Search Team
Date: 2026-10-02

## What this project is

Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. 

❓ [critique Q1] What is this meant to learn?: `Type:` says exploratory, which means the project exists to learn something (grounding/knowledge/project-kinds.md). This line says what it does, not what you want to find out. What question should this project answer, and what finding would make you stop, change course, or turn it into an operational service?

This project exists to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more often than the keyword search each catalog already offers. If it does not, we stop; if it does, we decide whether to run it as a service.

❓ [critique C1] An API, an app, or both?: README.md describes "a collection-search-only STAC API" that STAC Browser can sit on. The goals below talk about an "interface" with sorting, pagination and code hints, and streamlit_app.py is a separate demo UI. Two tempting directions pull apart here. A: the product is a STAC-compatible API, and natural-language search is something any STAC client can call. B: the product is a search app for people, and the API is just its back end. Which is it? The answer decides who the goals are written for.

The product is the API: natural-language collection search that any STAC client can use. The Streamlit app is a demo of it, not a product.

## Who it is for

Scientists who want to such multiple stac catalogs. 

❓ [critique Q2] Which scientists, and what do they do today?: "Scientists" covers a remote-sensing expert who knows collection IDs and a domain scientist who does not know what STAC is. They need different things: one wants to skip the catalog hopping, the other needs plain-language queries to work at all. Who is the first user, and what do they do now when they look for data across catalogs?

Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords.

❓ [scope Q2] Whose catalogs?: A deployment searches the catalogs in its configuration (docker-compose.yml: MAAP, eoAPI, CMR STAC), and any caller can pass a different list with `apis` (core.py `_resolve_apis`). Is this a search over a chosen set of catalogs that someone curates for these users, or a tool that works over whatever STAC APIs the user brings? They serve different people: one who does not want to think about catalogs at all, and one who already knows which catalogs they want searched.

It searches a curated set of catalogs chosen for one community. Users do not need to know or pick the catalogs.

## Goals

Relevant data surfaced and ranked across multiple stac catalogs. Simultaneous multi-API search across configured STAC endpoints

❓ [critique Q3] Which of these are outcomes?: Only this first goal says what changes for the user. The six below are features (health diagnostics, per-API filtering, pagination), and nothing says which ones serve the direction at the bottom of the file. "Relevant" is also undefined: relevant by whose judgement? Assume a year from now every feature shipped and scientists still did not use it. Which outcome did the file fail to name? Choose: keep one or two outcomes here and move the features to the ConOps, or keep the list and say which feature serves which outcome.
 A scientist describing their need in plain words finds the collection they would have chosen by hand, near the top, without knowing which catalog holds it. The other items are features that serve this, and are listed in the ConOps.

❓ [scope C1] Better ranking, or better finding?: Candidates come only from each upstream's own keyword `q` search, one request per expanded term (search.py, pipeline.py step 5). The LLM chooses the words and reorders what comes back. A collection that none of those words hits never reaches the ranker. Does this goal mean putting what upstream keyword search returns in a better order, or also finding collections that keyword search misses? The second needs something the upstream catalogs do not offer today.

➡️ This phase tests whether better words and better ordering, on top of each catalog's own search, are enough. If the right collection is often never returned at all, that is a finding to act on, not a bug to hide.

## Non-goals

Data analysis, data visualization. 

❓ [critique Q4] Item search and your own index: two non-goals are missing. README.md says this API "does not support item search", yet a goal above offers code hints "for item search workflows". And a tempting proposal is coming: copy every upstream collection into a local index with embeddings, instead of querying the live APIs on every search. Is item search out? Is holding your own index or copy of upstream metadata out?

Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs.

## Constraints

- Anything that rules out otherwise reasonable approaches: platform, data,
  compliance, deadline, team size, an existing system it must live beside.

❓ [critique Q5] What rules approaches out?: This section is still the template. The code depends on a hosted LLM (src/stac_fastapi/collection_discovery/llm/client.py) and on upstream catalogs you do not control. Is depending on a commercial LLM acceptable for this project? Must the API stay compliant with the STAC API spec so existing clients keep working? Is there anything it must live beside?

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs.

## Direction

Focus is getting users to the correct dataset leveraging semantic search. 

❓ [critique C2] Is "semantic search" the goal or one method?: pipeline.py does LLM query decomposition, term expansion into keyword `q` searches on each upstream, then LLM re-ranking. There are no embeddings. If "semantic search" names a method, the direction already disagrees with the code. If it names the outcome ("the right dataset"), the method is open. Which one does this line commit to? And if the two pull apart, which wins: the right dataset fast, or the right dataset even if slow?

The direction is getting users to the correct dataset; how we interpret their words (LLM expansion, re-ranking, embeddings) is a method we are free to change. When accuracy and speed conflict, accuracy wins.

❓ [scope Q1] An answer or a result list?: In natural-language mode the API returns one re-ranked list cut at `limit`, with no token pagination (core.py, "Token pagination is not supported in this mode"). Keyword mode pages through every match, and the goals list pagination. Is natural-language search meant to hand back a short best-guess list, or every match in a better order that the user can page through? They are different products with different costs per query.

 Natural-language search returns a short list of the best matches, each with its reason. A user who wants every match uses keyword search with paging.
