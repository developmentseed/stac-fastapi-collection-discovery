# Intent NNN: <short title>

<!--
Copy intent/TEMPLATE/ to intent/NNN-<slug>/ before the work starts,
where NNN is the issue number, so two branches never pick the same one.
One folder per feature or bugfix, one folder per PR, one spec.md and one
plan.md in it. You own this file; whether an agent may draft it for you
follows the Grounding section of CLAUDE.md. The personas write
their questions into it, each under the line it is about; you answer one by
rewriting that line in your own words and deleting the block.
The plan is drafted from it once it has converged and is agreed. The review
before push grades the PR against Completion criteria and Non-goals.
Delete these comments as you go.
-->

Status: draft | agreed | abandoned | superseded by NNN
Agreed with: <reviewer or maintainer>
Date: <YYYY-MM-DD>

<!-- Code-free. No file paths, no function names. Someone who does not code
should be able to agree to it. -->

## Motivation

Why this work exists. The problem, not the solution. The context that would
otherwise shape the implementation without anyone writing it down.

## Current process

How it works today, in behaviour terms. Leave out for new work.

## Task

What changes, in behaviour terms.

## Appetite

How much time this is worth. When it runs out, the task shrinks, not the
calendar.

## Completion criteria

How anyone knows it is done. Observable outcomes. The review before push
grades each one.

## Non-goals

What this deliberately does not do. The fence that stops a well-meant change
from taking the work somewhere nobody agreed to.

## Rabbit holes

What looks in scope and is not, or what could eat the appetite.

## Open questions

Anything unresolved. Delete the section when empty.

## Decisions

Dated entries, newest first. What was settled for this intent and the evidence
behind it. A source outside the repo is named: a URL, a paper, a package and
its version. When implementation finds this spec wrong, the change is recorded
here before the plan or the code moves: added, modified or deleted, with the
date. A deferred item names the intent it moves to.

- YYYY-MM-DD: <what was decided, on what evidence>
