# SFO Requirements Traceability Matrix

> Version: 0.9.0 | Date: 2026-08-25 | Evidence quality: DIRECT = automated test, STRONG = manual verified, INDIRECT = code inspection

## Core Requirements

| ID | Requirement | Implementation | Test | Evidence | Status |
|----|-------------|---------------|------|----------|--------|
| SFO-REQ-001 | Never delete or overwrite user files | `validate_plan` containment + `Executor` | `test_plan_destination_outside_root_refused`, `test_plan_source_inside_other_actions_moved_directory_refused`, 20 security tests | DIRECT | VERIFIED |
| SFO-REQ-002 | Preview before execute | `cmd_preview` (read-only) + `cmd_organize` (confirm) | `test_preview_returns_pure_json`, CLI suite | DIRECT | VERIFIED |
| SFO-REQ-003 | Durable transaction journal | `TransactionJournal` with fsync JSONL | `test_crash_midway_...`, drill tests | DIRECT | VERIFIED |
| SFO-REQ-004 | Per-action verification | `Executor._verify` inode+size check | `test_operation_id_correlates_...`, convergence test | DIRECT | VERIFIED |
| SFO-REQ-005 | Undo reverses moves | `cmd_undo` reads journal, reverses | Undo suite tests | DIRECT | VERIFIED |
| SFO-REQ-006 | Recovery is report-only | `cmd_recover` + `assess_operation` | `test_crash_midway_...`, `test_recovery_scan_and_cli_are_idempotent` | DIRECT | VERIFIED |
| SFO-REQ-007 | Path containment within root | `validate_plan` + `SecurityPolicy` | Security suite: path traversal, symlink escape | DIRECT | VERIFIED |
| SFO-REQ-008 | fcntl root locks | `RootLock` in `Executor` | Indirect via CLI convergence | INDIRECT | VERIFIED |
| SFO-REQ-009 | Stdlib-only (no runtime deps) | Zero third-party imports in src/ | Static analysis: `grep` import audit | DIRECT | VERIFIED |
| SFO-REQ-010 | Local-only (no network) | Zero network imports in src/ | Static analysis: `grep` for `socket`, `http`, `urllib` | DIRECT | VERIFIED |

## Security Requirements

| ID | Requirement | Implementation | Test | Evidence | Status |
|----|-------------|---------------|------|----------|--------|
| SFO-REQ-SEC-001 | Symlink escapes blocked | `SecurityPolicy.check_path` | `test_symlink_...` security suite | DIRECT | VERIFIED |
| SFO-REQ-SEC-002 | Path traversal blocked | `PathOutsideRootError` | `test_path_traversal_...` security suite | DIRECT | VERIFIED |
| SFO-REQ-SEC-003 | Destination containment | `validate_plan` | Mutation test kills containment in both suites | DIRECT | VERIFIED |
| SFO-REQ-SEC-004 | DB 0600 permissions | `Database.connect` chmod | `test_database_permissions_enforced` | DIRECT | VERIFIED |
| SFO-REQ-SEC-005 | Crash records bounded | `MAX_RECORDS=10` + prune | `test_crash_records_are_bounded` | DIRECT | VERIFIED |
| SFO-REQ-SEC-006 | No secrets in scan | Static scan of repo | Secret scan: grep for credentials | DIRECT | VERIFIED |

## Data-Integrity Requirements

| ID | Requirement | Implementation | Test | Evidence | Status |
|----|-------------|---------------|------|----------|--------|
| SFO-REQ-DI-001 | Post-move verification | `Executor._verify` | Convergence test: count reaches 0 | DIRECT | VERIFIED |
| SFO-REQ-DI-002 | Partial failure status | `OpStatus.PARTIAL` | CLI partial-failure tests | DIRECT | VERIFIED |
| SFO-REQ-DI-003 | Interrupted op detection | `assess_operation` vs SUMMARY | `test_crash_midway_...` | DIRECT | VERIFIED |
| SFO-REQ-DI-004 | Recovery idempotent | `pending_recoveries` is read-only | `test_recovery_scan_and_cli_are_idempotent` | DIRECT | VERIFIED |
| SFO-REQ-DI-005 | Op-ID correlation | meta table `opmap:{id}` | `test_operation_id_correlates_journal_database_and_cli` | DIRECT | VERIFIED |

## Privacy Requirements

| ID | Requirement | Implementation | Test | Evidence | Status |
|----|-------------|---------------|------|----------|--------|
| SFO-REQ-PRI-001 | Zero network communication | No imports in src/ | Static grep | DIRECT | VERIFIED |
| SFO-REQ-PRI-002 | No file contents in logs | `safe_text` escapes | Code inspection | INDIRECT | VERIFIED |
| SFO-REQ-PRI-003 | Crash records capped | message 400 chars, traceback 2400 | `test_crash_record_does_not_leak_hostile_argv` | DIRECT | VERIFIED |
