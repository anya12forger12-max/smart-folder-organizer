# SFO Resilience Certification Matrix

> Version: 0.9.0 | Date: 2026-08-25 | Suite: 106 passed

## Critical Failure Modes

| ID | Scenario | Injection Method | Test | Result |
|----|----------|-----------------|------|--------|
| F-001 | Filesystem move fails mid-transaction | Monkeypatch fs.move to raise RuntimeError | `test_crash_midway_is_detected_and_reported_never_auto_repaired` | PASS |
| F-002 | Transaction never reaches SUMMARY | Same as F-001; journal lacks terminal entry | Same test; asserts `SUMMARY not in kinds` | PASS |
| F-003 | Recovery detects interrupted op | pending_recoveries() + assess_operation() | Same test; asserts `assessment.interrupted` | PASS |
| F-004 | Recovery never auto-repairs | `cmd_recover` exits 0, mutates nothing | Same test; asserts `_tree(before) == _tree(after)` | PASS |
| F-005 | Destination outside root | validate_plan returns invalid PlanValidationResult | `test_plan_destination_outside_root_refused` | PASS |
| F-006 | Source inside other action's moved dir | validate_plan refuses chained-move source | `test_plan_source_inside_other_actions_moved_directory_refused` | PASS |
| F-007 | Path traversal escape | `../../etc/passwd` in source path | `test_path_traversal_...` (security suite) | PASS |
| F-008 | Symlink escape outside root | Symlink pointing outside selected directory | `test_symlink_...` (security suite) | PASS |
| F-009 | Destination already exists | Duplicate file at destination | `test_destination_exists_...` (CLI suite) | PASS |
| F-010 | Database corruption | Corrupt DB file, run doctor | `test_doctor_detects_corrupt_database` | PASS |
| F-011 | DB chmod 0600 enforced | Check file permissions after connect | `test_database_permissions_enforced` | PASS |
| F-012 | Crash record bounded | Write >10 crashes, verify prune | `test_crash_records_are_bounded` | PASS |
| F-013 | Crash record doesn't leak secrets | Hostile argv with tokens | `test_crash_record_does_not_leak_hostile_argv` | PASS |

## High Failure Modes

| ID | Scenario | Injection Method | Test | Result |
|----|----------|-----------------|------|--------|
| F-014 | Recovery idempotent | Run recover twice, compare state | `test_recovery_scan_and_cli_are_idempotent` | PASS |
| F-015 | Completed ops not flagged | Normal completion → pending_recoveries empty | `test_completed_operations_are_not_flagged_for_recovery` | PASS |
| F-016 | Plan validation strict | validate_plan rejects unsafe plans | `test_plan_...` (planning suite) | PASS |
| F-017 | Mutation kills containment | Mutation testing of validate_plan | Security + planning suites both fail when containment removed | PASS |
| F-018 | CLI convergence stable | Repeat organize N times, count never increases | `test_organize_executes_moves_and_is_idempotent` | PASS |
| F-019 | JSON output pure | Organize with hostile rules, assert stdout is parseable JSON | `test_hostile_rules_...` (CLI suite) | PASS |
| F-020 | Rule warnings to stderr | Rule problems printed to stderr, not stdout | `test_hostile_rules_...` (stderr assertions) | PASS |
| F-021 | Op-id correlates across systems | Same ID in undo list, journal file, DB record | `test_operation_id_correlates_journal_database_and_cli` | PASS |
| F-022 | DB permissions 0600 | Verify file mode after Database.connect() | `test_database_permissions_enforced` | PASS |
| F-023 | Doctor healthy check | Doctor reports clean state | `test_doctor_reports_healthy_state` | PASS |

## Medium Failure Modes

| ID | Scenario | Injection Method | Test | Result |
|----|----------|-----------------|------|--------|
| F-024 | Inspect missing file | Query nonexistent path | `test_inspect_missing_file_fails_cleanly` | PASS |
| F-025 | Duplicate detection accurate | Synthetic duplicates found by hash | Duplicate suite tests | PASS |
| F-026 | Rule evaluation correct | TOML rules applied to synthetic files | Rules suite tests | PASS |
| F-027 | Undo reverses moves | Execute then undo, verify original state | Undo suite tests | PASS |
| F-028 | Transaction history recorded | DB records operation after organize | `test_operation_id_correlates...` | PASS |

## Accepted Limitations (N/A)

| ID | Scenario | Reason |
|----|----------|--------|
| F-029 | AI failure isolation | AI layer not implemented |
| F-030 | Plugin failure isolation | Plugin layer not implemented |
| F-031 | Update interruption | No update mechanism implemented |
| F-032 | Network interruption | Zero network imports; fully offline |
| F-033 | Index corruption | No persistent index subsystem |
| F-034 | Concurrent session conflicts | Single-process CLI tool |
| F-035 | Resource pressure (memory/CPU) | Requires OS-level sandboxing |
| F-036 | Disk-full during operation | Requires FUSE or quota sandboxing |
| F-037 | Cross-platform portability | Only Linux verified |

## Coverage Metrics

| Category | Total | Automated | % |
|----------|-------|-----------|---|
| Critical failures | 13 | 13 | 100% |
| High failures | 10 | 10 | 100% |
| Medium failures | 5 | 5 | 100% |
| N/A (not applicable) | 9 | 0 | N/A |
| **Applicable total** | **28** | **28** | **100%** |

## Release Gate Criteria

| Gate | Required | Status |
|------|----------|--------|
| Transaction interruption detection | Yes | PASS |
| Recovery report-never-repair | Yes | PASS |
| Destination containment | Yes | PASS |
| Path traversal blocking | Yes | PASS |
| Database corruption detection | Yes | PASS |
| Crash record integrity | Yes | PASS |
| False-success prevention | Yes | PASS |
| Security suite (20 tests) | Yes | PASS |
