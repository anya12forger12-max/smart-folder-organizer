# SFO Test Matrix

Status after quality-engineering increment (v0.9.0). Counts are exact at
time of writing; run `python3 -m pytest -q` for the live number
(currently 95 passed, 0 failed, ~2 s).

## Layers

| Layer | Location | Count | Scope |
|---|---|---|---|
| Rules unit | `tests/rules/` | 8 | priority determinism, conflicts, literal matching |
| Planning validation | `tests/planning/` | 9 | staleness, protected, dup destinations, containment, chains |
| Undo service | `tests/undo/` | 6 | roundtrip, refusals, history, occupied destination |
| Duplicates | `tests/duplicates/` | 15 | grouping, sizes, read-only behavior |
| Inspection | `tests/inspection/` | 16 | type detection, mismatch, hashing |
| Security adversarial | `tests/security/` | 20 | traversal, races, tampering, corruption, containment |
| CLI contracts | `tests/cli/` | 21 | exit codes, JSON purity, convergence, lifecycle |

## Stable identifiers

Test ids use `<AREA>-<NNN>` in test docstrings/references:

- `FS-0xx` filesystem/scanner boundary (symlink escape, special files)
- `TX-0xx` transaction execution/journaling (collision, journal integrity)
- `UN-0xx` undo/refusal paths
- `SEC-0xx` adversarial suite cases (ordered as in the file)
- `CLI-0xx` CLI contract cases
- `PLN-0xx` planning validation cases
- `DUP-0xx`, `INS-0xx` duplicates/inspection units

## Critical-path coverage map

| Invariant | Enforced by | Tests |
|---|---|---|
| No mutation outside root | preflight + `validate_plan` containment | PLN, SEC (mutation-verified: killing the check fails both suites) |
| No overwrite | executor collision refusal | TX, SEC forward-collision |
| Chained moves refused | `validate_plan` moved-dir detection | PLN, SEC |
| Hostile rules neutralized | rule validator + wholesale refusal | SEC parametrized, CLI hostile-rules |
| Journal survives crashes/tampering | strict `load_journal`, torn-tail tolerance | SEC corruption/tamper cases |
| Undo never invents actions | identity checks + destination checks | UN, SEC tampered-journal |
| Read-only commands mutate nothing | tree snapshots | CLI preview/duplicates, DUP |
| JSON output stays pure JSON | warnings to stderr | CLI (fixed: `rule problem:` leaked to stdout) |
| Organize converges | repeat runs decrease to stable zero | CLI organize |

## Mutation checks performed

1. Disabled destination-containment in `validate_plan` → failed 1 test
   (planning only). **Gap fixed**: added independent security-suite
   coverage; re-run kills tests in two suites.
2. Earlier increments: disabled symlink-escape handling → FS tests fail;
   relaxed journal parsing → SEC corruption tests fail.

## Known gaps (honest)

- Interruption/crash-point testing is simulated (torn writes), not real
  SIGKILL-at-instruction granularity.
- No property-based/fuzz framework yet; fuzzing is manual/adversarial.
- GUI does not exist yet, so no GUI E2E.
- Performance benchmarks are ad-hoc probes, not automated regression gates.
