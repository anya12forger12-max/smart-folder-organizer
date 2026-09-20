# SFO Specification Cleanup Plan

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
>
> This is the plan only — per audit rule, no changes are implemented here;
> implementation waits for explicit instruction.

## 1. Duplicates to merge / reference
| Item | Action | Why |
|------|--------|-----|
| Governance loop (DUP-003) | **MERGE** into `docs/continuous-validation-matrix.md` | One canonical loop; later phases reference it |
| Guardrail clauses (DUP-001/002) | **KEEP** | Intentional cross-reference, contract semantics |
| Test count claim (DUP-007 / CON-001) | **CORRECTED / RESOLVED** | Earlier audit passed wrongly claimed 94; pytest confirms **106** (parametrized expansion). Baseline unchanged |

## 2. Contradictions to resolve (need decision — not auto-resolved)
| ID | Required decision | Proposed resolution |
|----|-------------------|---------------------|
| CON-001 | RESOLVED — not a real contradiction; pytest confirms 106 (parametrized). Audit's 94 claim retracted | Gate dot-count heuristic fixed; baseline 106 unchanged |
| CON-002 | Reframe "backup certified" to "journal-based data-safety certified" | **Recommended: reframe doc language** |
| CON-003 | Clarify full-certification gate scope | **Recommended: full certification only for behavior/critical changes** |

## 3. Missing requirements (report only — no invention)
| Gap | Type | Action |
|-----|------|--------|
| GAP-001 test-count heuristic | Defect (soft) | FIXED — gate parses real summary; verified 106 |
| GAP-004 backup-vs-journal wording | Doc accuracy | Reframe (P1/P2) |
| GAP-002 architecture doc | Doc clarity | Optional create (P2) |

## 4. Outdated requirements
- None found obsolete; the journal-based recovery model and local-only/privacy
  model remain current. No feature has been superseded.

## 5. Terminology to standardize
- "backup" → "journal-based recovery / data-safety" where no backup exists.
- Standardize "production operation" terminal-wording.

## 6. Dependency-order changes
- None. Original phase ordering (engineering → resilience → release → go-live
  → maintenance → governance) is coherent; later phases correctly depend on
  earlier evidence.

## 7. Documentation updates
- `scripts/release-gate.py`: **DONE** — dot-count heuristic replaced with parsing pytest's authoritative "N passed" summary; baseline 106 unchanged (now verified correct).
- `docs/*`: no "106→94" count corrections needed (that audit finding was retracted); **do** reframe "backup" phrasing per CON-002.

## 8. What we deliberately do NOT do (NO-INVENTION)
- No concurrency, no telemetry, no auth, no auto-update, no backup, no network
  — these are correctly absent for a local single-user CLI.
