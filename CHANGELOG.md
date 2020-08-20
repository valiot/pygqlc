## [1.2.1] - 2020-10-20
### Added
- Add a Singleton metaclass to the helper_modules module

### Removed
- Singleton-decorator dependencie

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