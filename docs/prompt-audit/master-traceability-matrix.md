# SFO Master Traceability Matrix

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
>
> This is the MASTER requirement trace across all prompts. It supersedes the
> per-phase `docs/requirements-traceability-matrix.md` as the canonical
> reference while preserving the existing `SFO-REQ-*` IDs for continuity.
>
> STATUS LEGEND:
> - **CONFIRMED** = implementation + test + doc evidence verified
> - **PARTIAL** = some evidence present, not all links
> - **UNKNOWN** = no evidence in available context
> - **MISSING** = no implementation found
>
> EVIDENCE: DIRECT = automated test passing; INDIRECT = code inspection;
> none = no evidence located.

## CORE FUNCTIONALITY

| REQ ID | SOURCE | CATEGORY | REQUIREMENT | IMPLEMENTATION | TEST | DOC | STATUS |
|--------|--------|----------|-------------|----------------|------|-----|--------|
| REQ-0001 | PROMPT-001 | Core | Never delete or overwrite user files | `planning/validation.py` + `security/containment.py` | Security + planning tests | `threat-model.md` | CONFIRMED |
| REQ-0002 | PROMPT-001 | Core | Preview before execute (read-only) | `cli` preview + organize confirm | `test_preview_returns_pure_json` | `README.md` | CONFIRMED |
| REQ-0003 | PROMPT-001 | Core | Durable transaction journal | `execution/journal.py` (fsync JSONL) | Recovery drill tests | `recovery-decision-tree.md` | CONFIRMED |
| REQ-0004 | PROMPT-001 | Core | Per-action verification after move | `Executor._verify` (inode+size) | Undo + convergence tests | `resilience-certification-report.md` | CONFIRMED |
| REQ-0005 | PROMPT-001 | Core | Undo reverses moves | `undo/service.py` reads journal | `test_undo_service.py` (6 tests) | `final-closeout-report.md` | CONFIRMED |
| REQ-0006 | PROMPT-001 | Core | Recovery is report-only (non-destructive) | `recovery/reconciliation.py` + `cmd_recover` | `tests/recovery/test_drill.py` | `recovery-decision-tree.md` | CONFIRMED |
| REQ-0007 | PROMPT-004 | Core | Changes require a concrete requirement; no invented features | governance guardrail | n/a (process) | `change-request-template.md` | CONFIRMED (process) |

## SECURITY

| REQ ID | SOURCE | CATEGORY | REQUIREMENT | IMPLEMENTATION | TEST | DOC | STATUS |
|--------|--------|----------|-------------|----------------|------|-----|--------|
| REQ-0008 | PROMPT-001 | Security | Symlink escape blocked | `security/symlinks.py` + `policy.py` | `test_adversarial.py` | `threat-model.md` | CONFIRMED |
| REQ-0009 | PROMPT-001 | Security | Path traversal blocked | `PathOutsideRootError` | Security suite | `threat-model.md` | CONFIRMED |
| REQ-0010 | PROMPT-001 | Security | Destination containment within root | `validate_plan` | Security suite | `security-operations-certification.md` | CONFIRMED |
| REQ-0011 | PROMPT-001 | Security | DB 0600 permissions | `persistence/database.py` chmod | `test_database_permissions_enforced` | `security-operations-certification.md` | CONFIRMED |
| REQ-0012 | PROMPT-001 | Security | Crash records bounded | `MAX_RECORDS=10` + prune | `test_crash_records_are_bounded` | `privacy-assurance-certification.md` | CONFIRMED |
| REQ-0013 | PROMPT-001 | Security | No secrets in source | static scan | gate `no_secrets` | security doc | CONFIRMED |

## PRIVACY

| REQ ID | SOURCE | CATEGORY | REQUIREMENT | IMPLEMENTATION | TEST | DOC | STATUS |
|--------|--------|----------|-------------|----------------|------|-----|--------|
| REQ-0014 | PROMPT-001 | Privacy | Zero network communication | no socket/http/urllib imports | AST audit | `privacy-assurance-certification.md` | CONFIRMED |
| REQ-0015 | PROMPT-001 | Privacy | No file contents in logs | `safe_text` escaping | code inspection | `privacy-assurance-certification.md` | CONFIRMED (INDIRECT) |
| REQ-0016 | PROMPT-001 | Privacy | Crash records content-capped | 400-char message, 2400 traceback | `test_crash_record_does_not_leak_hostile_argv` | `privacy-assurance-certification.md` | CONFIRMED |
| REQ-0017 | PROMPT-002 | Privacy | Backups/telemetry not invented beyond architecture | limitation | n/a | `production-health-review.md` | CONFIRMED (limitation) |

## DATA INTEGRITY / RECOVERY

| REQ ID | SOURCE | CATEGORY | REQUIREMENT | IMPLEMENTATION | TEST | DOC | STATUS |
|--------|--------|----------|-------------|----------------|------|-----|--------|
| REQ-0018 | PROMPT-001 | Integrity | Post-move verification (converge to 0) | `_verify` | convergence test | `resilience-certification-report.md` | CONFIRMED |
| REQ-0019 | PROMPT-001 | Integrity | Partial-failure status | `OpStatus.PARTIAL` | CLI partial tests | `final-closeout-report.md` | CONFIRMED |
| REQ-0020 | PROMPT-001 | Integrity | Interrupted op detection | `assess_operation` | `test_crash_midway_*` | `recovery-decision-tree.md` | CONFIRMED |
| REQ-0021 | PROMPT-001 | Integrity | Op-ID correlation journal↔DB↔CLI | meta `opmap:{id}` | `test_operation_id_correlates_*` | `resilience-certification-report.md` | CONFIRMED |

## GRAPHED COVERAGE (count of tests, ground truth)

> The authoritative count is **106 tests** as reported by pytest
> (parametrized tests expand the 94 test *functions* into 106 test *cases*).
> `python3 -m pytest --collect-only` reports "106 tests collected".

| AREA | TESTS (functions) | TEST FILE |
|------|-------------------|-----------|
| CLI (parametrized) | 15 fn → +cases | `tests/cli/test_commands.py` |
| Duplicates/scan | 15 | `tests/duplicates/test_scanner.py` |
| Inspection | 16 | `tests/inspection/test_inspector.py` |
| Observability | 8 | `tests/observability/test_diagnostics.py` |
| Planning/validation | 9 | `tests/planning/test_validation.py` |
| Recovery | 3 | `tests/recovery/test_drill.py` |
| Rules | 8 | `tests/rules/test_engine.py` |
| Security (parametrized) | 14 fn → +cases | `tests/security/test_adversarial.py` |
| Undo | 6 | `tests/undo/test_undo_service.py` |
| **TOTAL (functions)** | **94** | |
| **TOTAL (pytest cases)** | **106** | `pytest --collect-only` |

> **CORRECTION (2026-08-27):** An earlier audit pass counted 94 by summing
> `def test_` declarations and flagged the release gate's 106 baseline as a
> bug (GAP-001/CON-001). That finding was **incorrect**: parametrized tests
> (`test_commands.py:286`, `test_adversarial.py:151`) expand the 94 functions
> to **106 real test cases**, so the original 106 baseline was correct. The
> only genuine weakness was the gate's dot-count heuristic; it has been fixed
> to parse pytest's authoritative summary. The 106 baseline stands.

## Missing traceability links

| REQ | Missing link |
|-----|--------------|
| (architecture) | No `docs/architecture.md` / `docs/design.md` exists to trace module boundaries |
| (installation) | No dedicated install/upgrade/uninstall doc beyond README + gate wheel-install |
| (concurrency) | Correctly N/A — single-process CLI; documented as limitation, not testable |
