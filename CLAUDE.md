<!-- dev-collab-playbook:begin -->
## Grounding

This project uses the dev-collab-playbook plugin. The developer writes
`vision.md`, `conops.md` and each intent's spec. Agent personas write their
questions into those files, as ❓ blocks under the lines they are about. The
developer answers each by rewriting the line in their own words, then
deletes the block.

- `vision.md`, at the repo root: what the project is, for whom, goals, non-goals,
  constraints, direction. A page. The developer writes it. Every later question
  and review cites it.
- `conops.md`, at the repo root: how the system is run. Roles, environments,
  operating modes, numbers, data, change and rollback, verification, accepted
  risks. Every number, name, path and procedure the vision leaves out lives
  here. The developer writes it after the vision is agreed.
- `intent/NNN-<slug>/`: one folder per feature or bugfix, one per PR,
  copied from `intent/TEMPLATE/`. NNN is the issue number. `spec.md` is the developer's: why, what, done
  when, not this, and the decisions settled along the way. `plan.md` is
  drafted by the agent from the agreed spec, then edited and committed by the
  developer; implementation follows it. Same loop as the vision for both.
- `grounding/knowledge/`: team knowledge that comes with the plugin. Read
  it before questioning anything. `conventions.md` there is how the team
  builds; follow it when you draft a plan, write code or review. Do not
  edit it here; changes go to the plugin repo.
- `grounding/agents/`: one log per persona, of what it asked and how the
  developer answered. Personas write here. Nobody else does.

Rules for agents in this project:

- No project work before `vision.md` is written by the developer,
  says more than the template, and has been through the ground skill, then
  the same for `conops.md`. The same holds for the task's `spec.md`, then
  its `plan.md`, before the work starts. If a file is missing or still the
  template, say so and stop. Do not draft the vision, the ConOps or a spec.
- When the developer says a grounding file is written or updated, confirm
  their edits are done, then run the `dev-collab-playbook:ground` skill.
- `plan.md` is the one file you draft, and only when the ground skill reaches
  that step from an agreed spec. The developer edits and commits it.
- When implementation finds the spec wrong, stop. The developer records the
  change under Decisions in `spec.md`; then the plan is updated.
- When the developer says the work is ready to push, or asks for a review of
  a branch or PR, run the `dev-collab-playbook:review` skill. It needs the
  intent folder; without one, the review is a request for the spec.
- Never change the developer's text in `vision.md`, `conops.md` or a
  `spec.md`. The personas add and remove their own ❓ and ➡️ blocks there,
  through the ground skill, and nothing else.
- Never write into `grounding/agents/` yourself. Only the personas do,
  through the ground skill.
- Never commit. Suggest small commits and let the developer make them.
- Nothing goes out under the developer's name unread.

How hard these rules hold follows `Type:` in `vision.md`, defined in
`grounding/knowledge/project-kinds.md`. The type is the developer's
decision, recorded on that line. If the line is missing or still reads the
template's `operational | exploratory`, ask the developer which it is and
stop; they write it into `vision.md`. Never assume one. What relaxes by type
is stated here and nowhere else; the templates, the knowledge files and the
skills point back to this list.

- Operational: every rule above is a hard stop. No vision, ConOps, spec or
  plan means no work, whatever the size. A slip found in `git status` stops
  the work until the developer has resolved it.
- Exploratory: the same files, in the same order, and none is skipped
  either. Three things relax. You may draft the ConOps or a spec when the
  developer asks; they edit it, own it and agree it, and the vision stays
  theirs since it names the type. The ground skill runs critique and scope
  only. A slip found in `git status` is reported and the work goes on.

The personas cannot commit: they have no shell. The main agent can, and only
these rules stop it, so the ground skill looks at `git status` after every
run. The review judges the work by the spec, the plan, the tests it ran and
`conventions.md`, and by nothing else. Not by taste, and not beyond what
those show.

If no `dev-collab-playbook:*` skills are loaded, the plugin is not installed.
Trusting the folder registers the marketplace but does not install a plugin
served from a repository. Tell the developer to run
`claude plugin install dev-collab-playbook@dev-collab-playbook`, then stop.
<!-- dev-collab-playbook:end -->
