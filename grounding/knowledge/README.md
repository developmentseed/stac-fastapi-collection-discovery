# Knowledge

Team knowledge that ships with the plugin and lands in every project's
`grounding/knowledge/`.

- Human experts own this folder. Edit it in the plugin repo, not in a
  project. `tools/bootstrap.sh --check` flags a project copy that drifted,
  and `--update` refreshes it.
- Personas read it before questioning a project's vision. The agent
  follows `conventions.md` when it drafts a plan, writes code or reviews.
- One topic per file. Short. Plain words.
