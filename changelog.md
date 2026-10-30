## [Unreleased]

### Added
- `deployment/backup.sh` copies a git bundle of every branch and tag, the local `.env` and,
  with `BACKUP_DB`, the database into a timestamped folder, and keeps the newest ten.

## [1.2.0] - 2026-10-30

### Added
- A push through ntfy when a new APK arrives, by upload or as a file in the dist folder. Set
  `NTFY_URL` to turn it on; the topic is `NTFY_TOPIC` (default `apk-hoster`). A first start on an
  empty database sends nothing.

## [1.1.0] - 2026-08-21

### Added
- Guest user authentication via query parameters (`u=guest`, `p=guest`).
- Automatic creation of `guest` user on database initialization.
- `APK_ALIASES` (`old=new,old2=new2`) makes a renamed APK series keep answering under its old
  name. A series is identified only by the filename prefix of its uploads, so renaming one
  strands every copy already installed: those keep asking `/api/version` for the old name and
  are told they are up to date. An alias bridges that until the last install has been replaced
  by a build that asks for the new name. Aliases apply to a user's `apk_filter` as well, so a
  rename does not silently revoke access to the series.

### Changed
- The service no longer carries the name of the one app it happened to host. `APP_NAME` now
  defaults to `APK Hoster` instead of `ultrasonic` (which is what the login page showed on a
  deployment that never set it), the seeded non-admin account is configured through
  `DEFAULT_USER` / `DEFAULT_USER_PASSWORD` instead of the hardcoded `ultrasonic` user and its
  `ULTRASONIC_PASSWORD` variable, the protected-user list and the example `apk_filter`
  placeholders follow from those, and `/api/version` no longer defaults its `apk` parameter to
  a specific app - without one it returns the newest upload of any series.

### Migration
- Rename `ULTRASONIC_PASSWORD` to `DEFAULT_USER_PASSWORD` in the deployment `.env`, and set
  `DEFAULT_USER` to the account name that deployment already uses. Existing user rows are left
  untouched; only the seeding/permission refresh follows the new variables.

## [1.0.9] - 2026-07-04

### Added
- Comprehensive test suite in `tests/` covering core logic and API.
- Dev dependencies in `requirements-dev.txt`.

### Improved
- Code quality and maintainability through modular refactoring.
- Documentation with module and function-level docstrings.
- Adherence to PEP 8 standards (Pylint score > 9.0).
- Fixed environment-related setup issues for testing and linting.


## [1.0.8] - 2026-07-04

### Added
- Comprehensive test suite in `tests/` covering core logic and API.
- Dev dependencies in `requirements-dev.txt`.

### Improved
- Code quality and maintainability through modular refactoring.
- Documentation with module and function-level docstrings.
- Adherence to PEP 8 standards (Pylint score > 9.0).
- Fixed environment-related setup issues for testing and linting.


## [1.0.7] - 2026-07-04

### Added
- Comprehensive test suite in `tests/` covering core logic and API.
- Dev dependencies in `requirements-dev.txt`.

### Improved
- Code quality and maintainability through modular refactoring.
- Documentation with module and function-level docstrings.
- Adherence to PEP 8 standards (Pylint score > 9.0).
- Fixed environment-related setup issues for testing and linting.


## [1.0.6] - 2026-07-04

### Added
- Comprehensive test suite in `tests/` covering core logic and API.
- Dev dependencies in `requirements-dev.txt`.

### Improved
- Code quality and maintainability through modular refactoring.
- Documentation with module and function-level docstrings.
- Adherence to PEP 8 standards (Pylint score > 9.0).
- Fixed environment-related setup issues for testing and linting.


## [1.0.5] - 2026-07-04

### Added
- Comprehensive test suite in `tests/` covering core logic and API.
- Dev dependencies in `requirements-dev.txt`.

### Improved
- Code quality and maintainability through modular refactoring.
- Documentation with module and function-level docstrings.
- Adherence to PEP 8 standards (Pylint score > 9.0).
- Fixed environment-related setup issues for testing and linting.


## [1.0.4] - 2026-07-04

### Added
- Tabbed interface for APK list and Changelog
- Moved changelog to a separate tab at the top of the page


## [1.0.3] - 2026-07-04

### Added
- Tabbed interface for APK list and Changelog
- Moved changelog to a separate tab at the top of the page


## [1.0.2] - 2026-07-04

### Added
- Integrated versioning system (major, minor, patch)
- Project changelog displayed in the web UI
- Automated git tagging and pushing during release


## [1.0.1] - 2026-07-04

### Added
- Integrated versioning system (major, minor, patch)
- Project changelog displayed in the web UI
- Automated git tagging and pushing during release


## [1.0.0] - 2026-07-04

### Added
- Integrated versioning system (major, minor, patch)
- Project changelog displayed in the web UI
- Automated git tagging and pushing during release
