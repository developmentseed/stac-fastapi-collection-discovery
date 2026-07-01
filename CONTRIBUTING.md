# Contributing

## Installation

Install dependencies:

```bash
uv sync
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

## Testing

Run tests:

```bash
uv run pytest
```

We use pytest-recording to mock API calls with "pre-recorded" API responses.
When adding new tests use the ``@pytest.mark.vcr`` decorator function to indicate pytest-recording should be used.
Record the new responses and commit them to the repository.

```bash
uv run pytest -v -s --record-mode new_episodes
git add <new files here>
git commit -a -m 'new test episodes'
```

To update the existing recorded API responses:

```bash
uv run pytest -v -s --record-mode rewrite --block-network
git commit -a -m 'updated test episodes'
```

## Docs

To serve the documentation site run:

```bash
uv sync --group docs
uv run mkdocs serve -o
```

The docs site will be available in your browser at <http://localhost:3000>.

## Commit Messages and Versioning

This project uses [Conventional Commits](https://www.conventionalcommits.org/) for commit messages. This helps us automatically generate changelogs and determine version bumps.

### Commit Message Format

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

#### Types

- `feat`: A new feature. Triggers a release.
- `fix`: A bug fix. Triggers a release.
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code (white-space, formatting, etc)
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `test`: Adding missing tests or correcting existing tests
- `build`: Changes to build tooling or dependencies
- `ci`: Changes to CI configuration
- `chore`: Changes to the build process or auxiliary tools

Only `feat` and `fix` commits are included in release notes. Dependency and CI-only commits should use `build`, `ci`, or `chore` so release-please does not open a release PR for them.

#### Examples

```bash
feat: add support for multiple STAC API endpoints
fix: handle timeout errors in collection discovery
docs: update API documentation for new endpoints
```

### Releases and Versioning

Versions are automatically determined from git tags using [PDM's SCM versioning](https://pdm-project.org/latest/reference/build/#dynamic-versioning).

- Tagged commits represent releases (e.g., `v0.1.0`)
- Development versions show commit distance from the last tag (e.g., `0.1.dev14+ga7b98e8.d20250918`)
- Release PRs are managed by release-please
- A release PR is opened only when a `feat` or `fix` commit has landed on `main`
