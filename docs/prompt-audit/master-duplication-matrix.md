# SFO Master Duplication Matrix

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
>
> Per audit rule: repeated requirements are NOT deleted automatically. Each is
> classified and a KEEP / MERGE / REFERENCE / REMOVE recommendation is given.

| GROUP ID | REQUIREMENTS | PROMPTS | DUPLICATION TYPE | RECOMMENDATION | STATUS |
|----------|--------------|---------|------------------|----------------|--------|
| DUP-001 | "Do NOT invent features / do not invent a change" | PROMPT-003 §1/§2, PROMPT-004 §2, PROMPT-005 §45 | Intentional cross-reference (guardrail contract) | **KEEP** — identical rule restated as a contract clause for each phase; deduplicating would weaken the standing guardrail | CONFIRMED |
| DUP-002 | "Do NOT auto-generate the next prompt / stop when objective achieved" | PROMPT-004 §41, PROMPT-005 §52/§53, PROMPT-003 terminal | Intentional cross-reference | **KEEP** — these stop-the-loop clauses are necessary and correct | CONFIRMED |
| DUP-003 | Governance loop (OBSERVE→DOCUMENT / REQUIREMENT→VERIFY) | PROMPT-003 §1, PROMPT-004 §1 | Semantic repetition | **MERGE/REFERENCE** — keep one canonical loop in `docs/continuous-validation-matrix.md`; later prompts should reference, not restate | CONFIRMED |
| DUP-004 | "Never delete/overwrite user files" + containment | PROMPT-001, PROMPT-002, PROMPT-003 | Useful regression requirement | **KEEP** — this is the primary safety invariant (SFO-REQ-001); legitimate regression requirement, appears in security + planning trust-boundary tests | CONFIRMED |
| DUP-005 | Backup/recovery validation requested repeatedly | multiple earlier phases (backup & DR certification, recovery drills) | Semantic repetition | **KEEP as USEFUL REGRESSION** — recovery drills are legitimate repeated validation; **REMOVE** only if a phase asserted backup capability that does not exist (see GAP-004) | CONFIRMED |
| DUP-006 | Privacy: "zero network / no telemetry" re-verified in many phases | PROMPT-002/003 security & privacy sections | Intentional cross-phase validation | **KEEP** as regression; **REFERENCE** one canonical AST-audit procedure in `security-operations-certification.md` | CONFIRMED |
| DUP-007 | Test-count claims (106 vs claimed 94) | PROMPT-002 reports, audit pass | TRUE DUPLICATION — but of an **audit error**, not a real discrepancy | **CORRECTED** — 106 is correct (parametrized tests expand 94 functions to 106 cases); audit's 94 claim was wrong and has been retracted. No doc count changes needed | RESOLVED |

## Legend
- **Intentional cross-reference** — same rule needed in multiple contract frames; keep.
- **Useful regression requirement** — repeated validation that guards a critical invariant; keep.
- **True duplication** — same meaning, no added value, and (in one case) the duplicated value is wrong; correct/remove.
