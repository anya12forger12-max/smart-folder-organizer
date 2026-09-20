# SFO Master Contradiction Matrix

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
>
> Per NO-SILENT-RESOLUTION rule: no conflict is auto-resolved. Each is reported
> with the decision required.

| CONFLICT ID | REQ A | SOURCE A | REQ B | SOURCE B | CONFLICT | SEVERITY | DECISION REQUIRED | STATUS |
|-------------|-------|----------|-------|----------|----------|----------|-------------------|--------|
| CON-001 | "106 tests pass (RELEASE APPROVED)" | PROMPT-002 verdict / release-gate baseline | "94 tests" (claimed in an earlier audit pass) | pytest ground truth | **NOT A CONTRADICTION.** pytest reports **106 tests collected/passed**. An earlier audit pass wrongly counted 94 by summing `def test_` declarations, ignoring parametrized expansion (`test_commands.py:286`, `test_adversarial.py:151`). The 106 baseline is correct. The only real issue was the gate's dot-count heuristic, now fixed | **P4 (resolved)** | Retract the 94 claim; 106 stands | RESOLVED |
| CON-002 | "Backup and disaster-recovery certified" (phase title exists in the 40-phase list) | running phase list | "No backup feature exists" | `src/` inspection + honest scoping | "Backup certified" conflicts with "no backup functionality." The system's data-safety is journaling, not backup | **P2 (Medium)** | Decide: rename/reframe the phase as "journal-based data-safety & recovery certification" and explicitly state backup is out of scope | OPEN |
| CON-003 | "Full release certification" as an always-run gate | PROMPT-003 §4 | "Do not run unnecessary full certification for trivial changes" | PROMPT-003 §4 / PROMPT-004 §22 | The prompt both mandates full certification AND restricts it to justified cases | **P3 (Low)** | Decide: interpret as full certification required only for behavior/critical changes; trivial changes use targeted validation. This is a real but benign tension; document the rule | OPEN (clarify) |

## Resolved (no contradiction)
- "No invented features" vs "establish evolution process" — consistent (process without content).
- "Do not auto-generate next prompt" across 003/004/005 — consistent guardrail.
