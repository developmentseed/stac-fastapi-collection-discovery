# Operational concept

<!--
How the system is used and run day to day, by whom, under what conditions.
The vision says what and why; this says how it holds up in use. Numbers,
names, paths and procedures live here, not in vision.md. Write it after the
vision is agreed and before any spec. The personas write their questions into
this file, each under the line it is about. Answer one by rewriting that line
in your own words and deleting the block. Delete these comments as you go.
-->

Status: draft | agreed | superseded
Agreed with: <reviewer or maintainer>
Date: <YYYY-MM-DD>

## Users and roles

Who uses the system and how: through the interface, the API, notebooks, or
another system. Who operates it, who owns it, who is called. For each
neighbouring system, whether this team can change it alone. Who approves a
risky action, and what must be true before they do. How access is granted
and removed.

## Environments and dependencies

Each environment, where it runs, who hosts it, who uses it. The request path
hop by hop. Every outside service the promise rests on, and what stops
working when each one is down.

## Operating modes

Normal, demo, degraded, maintenance. What must keep working in each and what
users see. Who switches modes. What is probed to know the system is up, from
where, how often, and who is woken.

## Scenarios

Short walkthroughs of real use, start to finish, each with an ID that specs
and tests can point to. Normal use first, then what happens when something
goes wrong: what fails, how it is noticed, who responds, what users see, how
it returns to normal.

- OPS-0100: <who does what, and what they get back>
- OPS-1100: <what goes wrong, who responds, how it recovers>

## Numbers

The budgets and limits, each with where it is measured and where the last
measurement is recorded: latency, queue caps, the metric that means
overloaded and its value, anything a goal in the vision depends on.

## Data and access

What is stored, for how long, who can read it. Where secrets live and who
can read them. What is backed up and how it is restored.

## Change and rollback

Who can merge where, whether review is required, how a deploy happens, how a
version is swapped and rolled back, how users are told, what a stored result
records about the version that made it.

## Verification

What can be re-run to show the system still does what it did: fixed inputs
with expected outputs, checks after a version swap, what red-teaming leaves
behind.

## Support

Where users go for help and when it is staffed. Where the docs live. How an
incident is declared, escalated and reviewed afterwards. How the system is
retired and what happens to its data.

## Accepted risks

The threats and failures the team chooses to live with, each named with who
accepted it.

## Decisions

Dated entries, newest first. What was settled and on what evidence. A source
outside the repo is named: a URL, a paper, a package and its version.

- YYYY-MM-DD: <what was decided, on what evidence>
