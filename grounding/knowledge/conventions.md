# Conventions

How the team builds, and what the agent follows when it drafts a plan, writes
code or reviews a branch. Short on purpose.

## Working

- Implement only with a clear picture: an agreed spec and a plan the developer
  has committed. Nothing before that.
- Touch or create only what the plan needs. No side fixes, no extra files.
- Simple first. Add complexity when something forces it, and say what did.
- One plain paradigm per change. Do not mix styles to look clever.
- DRY: understand what exists, then reuse it. New code is the last option.
- Fail fast and loud. No silent fallbacks, no swallowed errors, no mocked
  outputs standing in for the real thing.
- If the logic is unclear, stop and ask early. Do not guess and keep going.
- Anything taken from outside the repo names its source: a URL, a paper, a
  package and its version. It goes in the Decisions entry, the plan step, the
  reviewer's Detail, or a comment beside the code that follows it.

## Code

- Delete dead code. Never comment it out.
- Comments are for why, not what. Overly commented code is an antipattern.
- A new behaviour comes with its test, and the test is run before the work
  is called done. Paste the output; do not summarise it.
- Log at the boundaries: inputs, outputs, errors. Enough to debug, no more.

## Docs

- Keep docs short and put what matters at the top. Do not flood a file.
- Plain words. Bullets over paragraphs where the content is a list.
- Prose from an agent goes through the humanizer before a human reads it.

## Commits and branches

- Branch off `develop`, come back with a pull request. See `branching.md`.
- The agent never commits. It suggests the line; the developer runs it. Suggest small commits. One change per commit, one short message to say what it is. Use bullet points iff needed.
