# Branching

How a project on the playbook uses branches.

- `main` is untouched. Nobody commits to it. It only receives `develop`.
- `develop` is the working branch and the root of the project. Everything integrates here first.
- Releases are tags on `main`.
- Work happens on a branch off `develop`. Each team member keeps their own
  intent folders and persona files on their branch and works them with the
  personas.
- A branch's grounding is grounded on the parent it forked from. The branch
  adds its own intent folder and its persona sections; it should not change
  the parent's vision, ConOps, knowledge or other intents. When planning or
  implementation finds it must, that is a gap worth recording: a human
  resolves the conflict deliberately, in the open, before the pull request.
  The review before push reports every such change so nobody merges one by
  accident.
- Contributing back means a pull request into the parent branch. Before it
  opens, the branch's `vision.md`, `conops.md`, `intent/` and `grounding/` are checked
  against the parent's, and the parent's against its parent, up to `develop`.
  Grounding must not diverge.
- Small commits. One change per commit, in plain words.
