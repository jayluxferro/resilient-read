# Release Guide

This project uses Semantic Versioning and manual release steps.

## 1) Prepare release

- Ensure tests pass: `uv run pytest`
- Update `CHANGELOG.md`:
  - Move relevant notes from `Unreleased` into the new version section.
  - Add release date in `YYYY-MM-DD` format.
- Bump version in `pyproject.toml`.

## 2) Commit release changes

```bash
git add pyproject.toml CHANGELOG.md
git commit -m "release: vX.Y.Z"
```

## 3) Tag the release

```bash
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin main --tags
```

## 4) Create GitHub release

- Open the new tag in GitHub.
- Create a release and paste changelog notes.

## Notes

- PyPI publishing is intentionally manual and out of scope for automation in this repository.
