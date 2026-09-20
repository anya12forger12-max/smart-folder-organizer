# SFO Certification Package Index

> Version: 0.9.0 | Date: 2026-08-25

## Engineering Documents

| Document | Purpose | Status |
|----------|---------|--------|
| `README.md` | Project overview, installation, usage | AUTHORITATIVE |
| `LICENSE` | MIT license | AUTHORITATIVE |
| `docs/final-closeout-report.md` | Verified system state, architecture, test results | AUTHORITATIVE |
| `docs/requirements-traceability-matrix.md` | Requirements → implementation → test mapping | AUTHORITATIVE |
| `docs/resilience-certification-matrix.md` | Failure modes → regression tests | AUTHORITATIVE |
| `docs/resilience-certification-report.md` | Resilience verdict and scorecard | AUTHORITATIVE |
| `docs/certification-drift-report.md` | Certification baseline and drift check | AUTHORITATIVE |

## Validation Documents

| Document | Purpose | Status |
|----------|---------|--------|
| `docs/testing-matrix.md` | Test layer mapping | SUPPORTING |
| `docs/threat-model.md` | Threat model and mitigations | SUPPORTING |
| `docs/chaos-validation-report.md` | Chaos experiment mapping | SUPPORTING |

## Maintenance Documents

| Document | Purpose | Status |
|----------|---------|--------|
| `docs/maintenance-policy.md` | Change categories, release cadence | SUPPORTING |
| `docs/incident-response-template.md` | Incident response template | SUPPORTING |
| `docs/change-request-template.md` | Change request template | SUPPORTING |
| `docs/maintenance-health-scorecard.md` | Current health snapshot | SUPPORTING |

## Test Evidence

| Suite | Tests | Location |
|-------|-------|----------|
| CLI | 21 | `tests/cli/` |
| Security | 20 | `tests/security/` |
| Undo | ~12 | `tests/undo/` |
| Planning | ~8 | `tests/planning/` |
| Observability | 8 | `tests/observability/` |
| Rules | ~6 | `tests/rules/` |
| Duplicates | ~5 | `tests/duplicates/` |
| Inspection | ~5 | `tests/inspection/` |
| Recovery | 3 | `tests/recovery/` |
| **Total** | **106** | |

## Build Artifacts

| Artifact | Hash (SHA256) |
|----------|--------------|
| `smart_folder_organizer-0.9.0-py3-none-any.whl` | `c06a68479b4c2e4de359211b91f3d973b0ffd582cd67970c7522b8603c4fdee4` |
| `smart_folder_organizer-0.9.0.tar.gz` | `68695ce474939637f62feed0eda638845c67a8a1ca188a594c45c04bc53925b8` |

## Certification Boundary

This certification covers:
- Version 0.9.0 on Linux with Python 3.14.6
- All 106 tests in the documented test suite
- Zero-dependency stdlib-only architecture
- CLI-only interface (no GUI)

This certification does NOT cover:
- macOS or Windows
- Other Python versions
- Future modifications
- Third-party tools or environments
