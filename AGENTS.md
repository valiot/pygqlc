# pygqlc — agent rules

`pygqlc` is a Python client for GraphQL APIs (sync + async over `httpx`, with
websocket subscriptions). These rules are for agents (and humans) working in
this repo.

## Environment

- Languages/tools are pinned in `mise.toml`: **Python 3.13** + **uv** (latest).
  Run `mise install` if the toolchain is missing.
- Dependencies are managed with **uv** (`pyproject.toml` + `uv.lock`, PEP 621, `hatchling` build backend). Never reintroduce Poetry/`requirements.txt`.
- The version is read dynamically from `pygqlc/__version__.py` (`[tool.hatch.version]`). Bump the string there — there is no version in `pyproject.toml`.
- The optional `valiotlogging` extra comes from a private index. Public/fork CI runs without it via the graceful fallback path, so **never make `valiotlogging` a hard import** — guard it.

## Workflow

- **TDD.** Write the failing test first, get it red for the right reason, then green, then refactor only if the code asks for it.
- **Tests:** `uv run pytest`. Async tests use `asyncio_mode = "strict"` — mark coroutine tests with `@pytest.mark.asyncio`. Keep tests fast and hermetic:
  **no real sockets, no sleeps** — the subscription/websocket regression tests are the model to follow.
- CI (`.github/workflows/ci.yml`) installs with `uv sync --frozen` (not `--all-extras`), so the lockfile must always be committed and current.
- `python-check-outdated.yaml` fails the build on outdated deps within constraints — run `uv lock --upgrade` on every PR and commit `uv.lock`.
  Transitive deps capped by a parent's range (e.g. `astroid` via `pylint`, `docutils` via `sphinx`/`twine`) are acceptable to leave at their max.

## Release each change

Follow semantic versioning. Before merging:

1. Bump `pygqlc/__version__.py` (patch for fixes/chores, minor for features).
2. Add a top entry to `CHANGELOG.md` using the existing `## [x.y.z] - YYYY-MM-DD` + `- [Fixed]/[Changed]/[Added]/[Dependencies]` style. State what changed, why, and any behavior shift.
3. Releases are tagged `vX.Y.Z` (see git tags); the maintainer cuts the tag.

## Code styling

- **Format:** `uvx ruff format` — `uvx ruff format --check` must pass.
- **Security:** `uvx bandit -r . -s B101 -ll --exclude $(find . -type d -name '.venv' | paste -sd, -)` must be clean. Suppress genuine false positives with a narrow `# nosec <ID>` plus a one-line comment explaining why (see the IPv4 egress bind in `GraphQLClient._update_client_params`).

## Design principles (DHH)

- **Majestic Monolith over premature abstraction.** Don't split a module until the pain of keeping it together is real and felt — not imagined.
- **Integrated, not isolated.** Prefer tests that exercise the real stack (integration tests) over elaborate unit-test scaffolding that mocks the world.
- **Omakase defaults.** Follow the conventions already in the codebase. Resist the urge to introduce a new pattern just because it exists elsewhere.
- **Clarity over cleverness.** Readable, obvious code beats terse or "clever" code every time. If you need a comment to explain *what* the code does (not *why*), rewrite the code.
- **The simplest thing that works.** No feature flags, no adapter layers, no dependency injection frameworks unless there is a concrete, present need. Three lines of obvious code beat an abstraction used once.
- **No speculative generality.** Don't design for hypothetical future requirements. Build what is needed now; refactor when the second use case arrives.
- **Small, named functions over anonymous pipelines.** Extract a well-named function when a block of code deserves a label; avoid deeply nested callbacks or chains that require mental unwinding.
- **Delete code fearlessly.** Unused code is a liability, not a safety net. Remove it; git history is the backup.

## Never do

- Never commit secrets, and never echo them into the conversation, files, or PR descriptions. Connection URLs/tokens belong in env vars.

## When you don't know

Read this file and the existing code/tests first. If still unsure between two reasonable approaches, pick one and explain the choice in the PR body rather than stalling to ask.
