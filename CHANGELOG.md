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
