# Vision

Status: accepted
Type: exploratory
Owner: Development Seed Federated Search Team
Date: 2026-10-02

## What this project is

  Performs federated collection searches across multiple STAC API endpoints at once using natural language queries. 


## Who it is for
Earth science researchers who know what data they need but not which catalog or collection holds it. Today they search each catalog's portal by hand, one at a time, with keywords. Our user wants data, not catalogs; that the search spans several catalogs is our concern, not theirs. Reaching the right collection is the whole job. Once the user has it, the upstream catalog's own tools get them the data, and we do not try to do that better.

## Goals
Scientists a presented with the right collection(s) via natural language search.


## Non-goals

Data analysis, data visualization. Item search is out: we hand the user off to the upstream API for items. We do not keep our own copy or index of upstream catalogs; every search queries the live APIs. Building is minimal as this is an MVP for now. 

## Constraints

It must stay a valid STAC API so existing STAC clients work against it. It may depend on a hosted LLM while it is exploratory. It cannot require any change to the upstream catalogs.


## Direction

Currently, the focus is getting users to the correct dataset across multiple STAC catalogs from a plain-language request like
"wildfires in 2023"


