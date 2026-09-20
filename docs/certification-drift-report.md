# SFO Certification Baseline and Drift Report

> Certified Version: 0.9.0 | Date: 2026-08-25 | Current: 0.9.0

## Certified Baseline

| Item | Value |
|------|-------|
| Version | 0.9.0 |
| Source | Uncommitted working tree (zero git commits) |
| Build | `python3 -m build --no-isolation` |
| Wheel SHA256 | `c06a68479b4c2e4de359211b91f3d973b0ffd582cd67970c7522b8603c4fdee4` |
| Test suite | 106 passed, 0 failed (1.45s) |
| Security suite | 20/20 passed |
| Python | 3.14.6 |
| Platform | Linux |
| Dependencies | Zero runtime (stdlib only) |

## Drift Check (Current vs. Certified)

| Area | Baseline | Current | Drift | Impact |
|------|----------|---------|-------|--------|
| Source code | 0.9.0 tree | Identical (no changes) | NONE | CERTIFICATION PRESERVED |
| Dependencies | Zero | Zero | NONE | PRESERVED |
| Build | wheel verified | Wheel built this run | NONE | PRESERVED |
| Tests | 106/106 | 106/106 | NONE | PRESERVED |
| Security | 20/20 | 20/20 | NONE | PRESERVED |
| Documentation | 8 docs | 8 docs | NONE | PRESERVED |
| Release | wheel + sdist | Same artifacts | NONE | PRESERVED |

## No Changes Since Certification

No source, test, dependency, build, or documentation changes have been made
since the certification baseline was established. All certification evidence
remains valid.

## Re-Certification Triggers

Certification must be reviewed if any of the following change:

1. Any file under `src/sfo/` is modified
2. Any file under `tests/` is modified
3. `pyproject.toml` dependencies change
4. Build tooling changes
5. Python version requirement changes
6. Platform support changes
7. Any security-sensitive code is touched

## Verdict

**CERTIFICATION PRESERVED** — No drift detected. Zero changes since baseline.
