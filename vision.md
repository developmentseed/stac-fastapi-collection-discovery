# Vision

Status: draft
Type: exploratory
Owner: Development Seed Federated Search Team
Date: 2026-10-02

## What this project is

  Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. This project exists
  to learn whether an LLM-assisted, natural-language search across several live STAC APIs gets scientists to the right collection more
  often than this API's own federated keyword search over the same catalogs, so a win is credited to the LLM and nothing else. If it
  does not, we stop; if it does, we decide whether to run it as a service.

  The product is the API. Its natural-language search is reached through the `query` parameter; plain STAC clients still work against it
  but get keyword search. The experiment runs through the Streamlit demo, kept to a query box, the ranked list and each match's reason,
  so what is judged is the API's ranking. The reason for each match is extra, and the result must stand without it.

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
