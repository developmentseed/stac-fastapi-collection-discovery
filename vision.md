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

Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. This project exists to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more often than the keyword search each catalog already offers. If it does not, we stop; if it does, we decide whether to run it as a service.


The product is the API: natural-language collection search that any STAC client can use. The Streamlit app is a demo of it, not a product.

## Who it is for

Scientists who want to such multiple stac catalogs. Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords.

It searches a curated set of catalogs chosen for one community. Users do not need to know or pick the catalogs.

## Goals

Relevant data surfaced and ranked across multiple stac catalogs. Simultaneous multi-API search across configured STAC endpoints.

## Non-goals

Data analysis, data visualization. Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs.

## Constraints

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs.

## Direction

Focus is getting users to the correct dataset leveraging semantic search. 
Natural-language search returns a short list of the best matches, each with its reason. A user who wants every match uses keyword search with paging.
