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

Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. This project exists to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more often than the keyword search each catalog already offers. If it does not, we stop; if it does, we decide whether to run it as a service. The baseline is this API's own federated keyword search over the same catalogs, so a win is credited to the LLM and nothing else.


The product is the API: natural-language collection search that any STAC client can use. The Streamlit app is a demo of it, not a product. The experiment measures scientists using the API through an existing STAC client; the reason for each match is extra, and the result must stand without it.

## Who it is for

Scientists who want to such multiple stac catalogs. Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords. Our user wants data, not catalogs; that the search spans several catalogs is our concern, not theirs.

## Goals

Relevant data surfaced and ranked across multiple stac catalogs. Simultaneous multi-API search across configured STAC endpoints.
Scientists reach the right collection more often than with the keyword search each catalog already offers.


## Non-goals

Data analysis, data visualization. Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs.

## Constraints

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs. Existing STAC clients must reach the natural-language search without any change on their side; staying valid but getting only keyword search is not enough.

## Direction

Focus is getting users to the correct dataset leveraging semantic search. 

❓ [critique C2] Is "semantic search" the goal or one method?: Non-goals rule out any index of upstream catalogs, and pipeline.py has no embeddings: the LLM rewrites the query, upstream keyword search finds candidates, the LLM re-ranks them. If that beats keyword search, does it matter that it is not "semantic"? If a true semantic method needed an index, which gives way: the method or the non-goal?

➡️ Focus is getting users to the correct dataset; the method is open, but the no-index non-goal holds.
Natural-language search returns a short list of the best matches, each with its reason. A user who wants every match uses keyword search with paging.

❓ [scope Q4] Is federated keyword search part of the product?: This line leans on keyword search with paging, and most of the existing code and the README features are that federated keyword mode. The goals name only the natural-language search, and line 18 says "if it does not, we stop". If the LLM does not win, does federated keyword search stop too, or is it a product in its own right that outlives the experiment?

➡️ Federated keyword search is the base the experiment stands on, not a goal; if the LLM does not win, the whole project stops.
