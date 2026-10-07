# Vision

Status: draft
Type: exploratory
Owner: Development Seed Federated Search Team
Date: 2026-10-02

## What this project is

Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. This project exists to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more often than the keyword search each catalog already offers. If it does not, we stop; if it does, we decide whether to run it as a service. The baseline is this API's own federated keyword search over the same catalogs, so a win is credited to the LLM and nothing else.


The product is the API: natural-language collection search that any STAC client can use. The Streamlit app is a demo of it, not a product. The experiment measures scientists using the API through an existing STAC client; the reason for each match is extra, and the result must stand without it.

## Who it is for
Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords. Our user wants data, not catalogs; that the search spans several catalogs is our concern, not theirs.

## Goals
Scientists reach the right collection(s)


## Non-goals

Data analysis, data visualization. Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs.

## Constraints

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs.

## Direction

Focus is getting users to the correct dataset leveraging semantic search. 
