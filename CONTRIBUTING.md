# Contributing

## Commit Message Format

This project uses [Conventional Commits](https://www.conventionalcommits.org/) to automate versioning and changelog generation.

### Format

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

- **feat**: A new feature (triggers minor version bump)
- **fix**: A bug fix (triggers patch version bump)
- **docs**: Documentation only changes
- **style**: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc)
- **refactor**: A code change that neither fixes a bug nor adds a feature
- **perf**: A code change that improves performance (triggers patch version bump)
- **test**: Adding missing tests or correcting existing tests
- **build**: Changes that affect the build system or external dependencies
- **ci**: Changes to CI configuration files and scripts
- **chore**: Other changes that don't modify src or test files

### Examples

```
feat: add support for custom label templates
fix: resolve printer connection timeout issue
docs: update installation instructions
refactor: simplify label rendering logic
perf: optimize image processing for faster printing
test: add unit tests for label validation
```

### Breaking Changes

For breaking changes, add `!` after the type/scope:

```
feat!: change API response format
```

Or include `BREAKING CHANGE:` in the footer:

```
feat: add new label format

BREAKING CHANGE: The old label format is no longer supported
```

## Development Setup

1. Install dependencies: `pip install -e .[dev]`
2. Install pre-commit hooks: `pre-commit install`
3. Make your changes following conventional commits
4. Push to your feature branch - semantic-release will handle versioning automatically

## Release Process

Releases are automated using semantic-release:

- **Patch** releases (0.0.X) for `fix:`, `perf:` commits
- **Minor** releases (0.X.0) for `feat:` commits
- **Major** releases (X.0.0) for breaking changes

The release process runs automatically on every push to the `main` branch.
