# Grounding

Team knowledge the plugin ships, and the personas' files. The plugin repo holds
the source copy; `tools/bootstrap.sh` puts it in each project, beside
`vision.md` and `intent/` at the repo root.

| Path | Who writes it | Refreshed by `--update` |
|---|---|---|
| `../vision.md` | the developer, from the template, once | no |
| `../conops.md` | the developer, from the template, once the vision is agreed | no |
| `../intent/TEMPLATE/spec.md` | copied per task; the developer writes the spec | yes |
| `../intent/TEMPLATE/plan.md` | copied per task; the agent drafts it from the agreed spec, the developer edits and owns it | yes |
| `knowledge/` | human experts, in the plugin repo | yes |
| `agents/` | the personas, one log each, in the project only | never copied |

`vision.md` and `conops.md` are filled templates, in the developer's words.
The personas write their questions into them, each under the line it is
about; the developer answers by rewriting that line and deleting the block.
The logs under `agents/` record what was asked and how it was answered.

An intent is a folder, `intent/NNN-<slug>/`, with one `spec.md` and one
`plan.md` in it and nothing else. The spec is human-owned and carries the
decisions settled for that task. The plan follows from the agreed spec and is
what implementation follows.
