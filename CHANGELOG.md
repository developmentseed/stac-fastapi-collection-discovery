# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0](https://github.com/developmentseed/stac-fastapi-collection-discovery/compare/stac-fastapi-collection-discovery-v0.3.0...stac-fastapi-collection-discovery-v0.4.0) (2026-05-07)


### Features

* add aws handler and extra deps ([#4](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/4)) ([af2fbf5](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/af2fbf5e8776118ee7a25804b035b33b9029c561))
* collect upstream api exceptions in a custom header ([#13](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/13)) ([fea27ea](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/fea27ea9728730edd5755ae1ca5b39d9d5a8fc69))
* MVP ([#1](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/1)) ([e6a0f46](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/e6a0f46f713479b1a965c252efdba21e44da7bf6))


### Bug Fixes

* add timeout to httpx clients ([#5](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/5)) ([3377e1b](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/3377e1b3f4cc3772ea3607e4e9f41f8879975f9c))
* follow redirects in httpx clients, better url joining, more verbose health check ([#6](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/6)) ([2e9158a](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/2e9158ad0d6c8a323f646884973df2a839b833a4))
* refactor `apis` resolution, raise HTTPExceptions ([#8](https://github.com/developmentseed/stac-fastapi-collection-discovery/issues/8)) ([888b615](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/888b6151347508ee80306bfee8159b8d11741213))


### Documentation

* fix app port in README ([cc8c6ea](https://github.com/developmentseed/stac-fastapi-collection-discovery/commit/cc8c6ea0fdcf492eac08c38a97d781a3d4cbd77b))

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
