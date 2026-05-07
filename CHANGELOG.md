# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-07

### Added

- Collect upstream API exceptions in a custom response header. ([#13](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/13))

### Changed

- Pin GitHub Actions to SHA digests (fix zizmor unpinned-uses). ([#11](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/11))

### Dependencies

- Bump `astral-sh/setup-uv` from 6 to 7. ([#9](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/9))
- Bump `actions/checkout` from 5 to 6. ([#10](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/10))
- Bump `astral-sh/setup-uv` from 7.6.0 to 8.1.0. ([#14](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/14))

## [0.2.3] - 2025-10-01

### Fixed

- Refactor `apis` resolution and raise `HTTPException`s properly. ([#8](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/8))

## [0.2.2] - 2025-09-19

### Added

- Add collection-search capabilities to upstream API health check info. ([#6](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/6))

### Fixed

- Follow redirects in httpx clients. ([#6](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/6))
- Handle url paths more robustly. ([#6](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/6))

## [0.2.1] - 2025-09-18

### Fixed

- Add timeout to httpx clients. ([#5](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/5))

## [0.2.0] - 2025-09-18

### Added

- Add AWS handler and extra deps. ([#4](https://github.com/developmentseed/stac-fastapi-collection-discovery/pull/4))

## [0.1.0] - 2025-09-18

### Added

- Initial release.
- Combine collection search results from multiple upstream STAC APIs.
- Support standard STAC collection search parameters (`bbox`, `datetime`, `limit`, `fields`, `sortby`, `filter`, free text).
- Token-based pagination across multiple APIs.
- Health check endpoint for monitoring upstream API availability and collection-search capability.

[0.3.0]: https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/developmentseed/stac-fastapi-collection-discovery/releases/tag/v0.1.0
