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
uv run mkdocs serve -a localhost:3000
```

The docs site will be available in your browser at <http://localhost:3000>.
