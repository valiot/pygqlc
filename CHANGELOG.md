# CHANGELOG

## [3.7.1] - 2026-05-28

- [Fixed] Non-dict payloads after `orjson.loads` (e.g. a server-emitted `null` or array) no longer crash `_sub_routing_loop` with an unhandled `AttributeError` at `message.get('type')` and kill the router thread. A `not isinstance(message, dict)` guard now sets `wss_conn_halted` and triggers the existing reconnect path. (OPS-3485)
- [Changed] Transient websocket errors during `recv` (`ConnectionResetError`, `BrokenPipeError`, `ConnectionAbortedError`, `WebSocketConnectionClosedException`) are now classified at WARNING level rather than ERROR with a full traceback. Functional behavior (catch, set `wss_conn_halted=True`, reconnect) is unchanged; only the log noise. Exception classes hoisted into a module-level `TRANSIENT_WS_ERRORS` constant for readability.
- [Fixed] A server-initiated `complete` frame for a subscription the user never unsubscribed no longer silently drops the subscription. The cleanup now removes subscriptions only on explicit user `unsubscribe()` (or server `error`); a server `complete` retains the registry entry so `_resubscribe_all()` restores it on the next reconnect. This makes pygqlc resilient to servers that send per-subscription `complete` as part of a graceful shutdown drain — which previously caused silent permanent loss of subscriptions across every server deploy until each client process restarted.
- [Changed] Replaced the prior subscription-loop test with deterministic regression tests covering non-dict payload, transient error log levels, generic error log level, valid message routing, and the retain-on-complete semantics, with negative-control verification that each test fails against the pre-fix code. Tests run in <100 ms with no real sockets or sleeps.
- [Changed] CI no longer installs the private `valiotlogging` extra (`uv sync --frozen` instead of `--all-extras`), so public/fork CI runs against the graceful-fallback path. Direct dependency refreshes (orjson 3.11.8 → 3.11.9, dev tooling) + `uv.lock` aligned with Palantir baseline.

## [3.7.0] - 2026-05-04

- [Changed] Migrated build/dependency tooling from Poetry to **uv** with the `hatchling` build backend. `pyproject.toml` rewritten to PEP 621; version is now read dynamically from `pygqlc/__version__.py`
- [Changed] All dependencies upgraded to their latest compatible versions; lockfile is now `uv.lock`
- [Added] `mise.toml` pinning Python 3.13 + uv for the project
- [Fixed] `GraphQLClient.close()` now closes the thread-local `httpx.Client` (previously only subscriptions were torn down — HTTP clients leaked until garbage collection)
- [Fixed] `_get_http_client()` recreates the cached client when it has been closed, so calling `close()` is no longer a one-way door
- [Fixed] Eliminated `ResourceWarning: unclosed socket` and unclosed-transport warnings in the test suite
- [Changed] CI workflows ported from Poetry to uv; all `uses:` actions bumped to current versions

## [3.6.2] - 2026-05-04

- [Fixed] `GQLResponseException` now includes the server's response body in the error message and as a `response_body` attribute, making it possible to diagnose authentication errors (e.g. 401) without extra debugging
- [Changed] Applies to both sync and async execution paths

## [3.6.1] - 2026-04-15

- [Fixed] `_get_messages` now returns `[]` when `data` is not a dict (e.g. a list), preventing `AttributeError: 'list' object has no attribute 'values'` when `data_flatten` returns a list for single-key mutation responses

## [3.6.0] - 2025-06-24

- [Fixed] Improved message extraction for labeled mutations - mutations with multiple labeled operations now properly extract error messages from nested response structures

## [3.5.5] - 2025-06-11

- [Dependencies]: Bump valiotlogging to 1.0 and limit below 2.0

## [3.5.4] - 2025-05-02

- [Dependencies]: Upgrade the `valiotlogging` to accept versions higher for ValiotLogging

## [3.5.3] - 2025-03-20

- [Added] Support for valiotlogging via optional dependency
- [Improved] Replaced print statements with structured logging
- [Added] Custom logger functionality
- [Improved] Added automatic traceback printing for ERROR level logs

## [3.5.2] - 2025-03-19

- [Fixed] Reduce print statements in the library

## [3.5.1] - 2025-03-10

- [Fixed] Set httpx logger to WARNING level to reduce verbose HTTP request logs in applications using this library

## [3.5.0] - 2025-03-06

- [Improved] Major performance optimizations (>50% faster)
  - Added LRU caching for data flattening operations
  - Optimized thread management and reduced sleep times in polling loops
  - Implemented connection pooling with thread-local HTTP clients
  - Improved async code with better connection reuse
  - Added proper resource cleanup with **del** method
  - Reduced memory allocations with reusable constants and data structures
  - Added exponential backoff for connection retries
  - Added orjson for much faster JSON serialization/deserialization

## [3.4.0] - 2025-03-05

- [Added] Async versions of the main API methods: `async_execute`, `async_query`, `async_query_one`, and `async_mutate`
- [Added] Tests for the async methods
- [Added] `ipv4_only` option to force IPv4 connections for environments with problematic IPv6 configurations
- [Added] `GQLResponseException` is now directly importable from the package root
- [Changed] Replaced the requests library with httpx (with HTTP/2 support) for better performance

## [3.3.0] - 2025-01-25

- [Added] GitHub Workflow to check for outdated packages on push
- [Changed] Update dependencies

## [3.2.0] - 2024-04-04

### Changed

- Update dependencies, mainly websockets to ^1.0

## [3.1.4] - 2023-08-16

### Fixed

- Bump `certifi` version to fix security vulnerability

## [3.1.3] - 2023-07-17

### Changed

- Add automatically generated `__version__` constant (from `poetry version <increment>`)

## [3.1.2] - 2023-07-17

### Changed

- Remove `__version__` constant from package exports

## [3.1.0] - 2023-03-27

### Added

- Execute subscription callback in a safe way (try/except)

## [3.0.5] - 2023-02-22

### Fix

- align dependencies to other valiot packages (valiotWorker/gstorm)

## [3.0.4] - 2023-02-17

### Fix

- Fix method to close subscriptions correctly

## [3.0.3] - 2023-02-14

### Fix

- Fix **version** string
- Fix bundling tools not including nested modules (`helper_modules`)

## [3.0.1] - 2022-07-31

### Fix

- Fixed race condition when a subscription is starting and \_sub_routing_loop is running.

## [3.0.0] - 2022-07-04

### Changed

- Upgrade GraphQL Subscriptions over WebSocket using `graphql-transport-ws` sub-protocol compatible with 627 (Breaking Change)

## [2.1.0] - 2022-02-04

### Added

- Add `post_timeout` configuration to avoid stale POST requests

## [2.0.4] - 2021-10-29

### Fix

- Upgrade dependencies in setup.py

## [2.0.3] - 2021-09-21

### Fix

- Outdated tests for latest version of valiot-app

### Chore

- Bump dependencies versions.

## [2.0.2] - 2020-09-02

### Fix

- Fixed helpermodule MODULENOTFOUND error.

## [2.0.1] - 2020-08-25

### Chore

- Change ownership to Valiot Organization

## [2.0.0] - 2020-08-25

### Added

- Add Documentation with sphinx
- Add validation in the testing resources

### Changed

- Change Singleton implementation from decorator to metaclass

### Fixed

- Dependencies have been set to be installed from certain compatible version

### Removed

- Singleton-decorator dependency

## [1.2.0] - 2020-07-08

### Added

- Configuration parameter websocketTimeout to be used when the connection is halted
- Method reset all subscriptions and websocket connection

### Fixed

- Websocket reconnection when halted with WebSocketTimeoutException

## [1.1.2] - 2020-03-26

### Fixed

- Websockets now send String ID instead of Int (for compatibility with Hasura and Apollo WS docs compliance)
- Reconnection to subscriptions when connection lost

## [1.1.1] - 2019-09-10

### Fixed

- Strip variable definition from mutation previous to Regex parsing to improve performance
- Convert to "null" when variable is None

## [1.1.0] - 2019-09-10

### Added

- Add batchMutation functionality (group several labeled mutations in a single transmission)

## [1.0.8] - 2019-09-02

### Fixed

- Add long description content type to be parsed correctly by pypi

## [1.0.6] - 2019-09-02

### Fixed

- Add long description to setup.py (it enables the description to display on pypi).
- Went open source! follow the project at: https://github.com/valiot/pygqlc

## [1.0.5] - 2019-09-02

### Fixed

- Bugfix closing procedure for GQL client (routing loop not closing properly).

## [1.0.4] - 2019-09-02

### Fixed

- Subscription message routing loop finishing when no subscription was active.

## [1.0.0] - 2019-09-01

### Added

- Working queries
- Working mutations
- Working subscriptions
