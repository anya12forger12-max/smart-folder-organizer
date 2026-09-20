# SFO Master Prompt Inventory

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
> **Auditor note:** This catalog lists ONLY prompts that actually exist in the
> available conversation/project context. Per audit rule, we do NOT invent
> prompts whose numbers are merely referenced. The earlier phase labels
> (e.g. "bubble sort", "only once", "avoid at all cost", "spherified",
> "certification drift", "seppeltsfield", "battery, and fast") are real supplied
> prompts earlier in the sequence that shaped the design but are not all fully
> reproduced here.

## Status Legend

| Status | Meaning |
|--------|---------|
| FOUND | Prompt exists and its requirements are implemented + evidenced |
| PARTIALLY FOUND | Prompt exists; some requirements implemented, some not fully evidenced |
| MISSING | Referenced but not present in context / no evidence of implementation |
| DUPLICATE | Substantially repeats another prompt |
| SUPERSEDED | A later prompt replaced its requirements |
| CONFLICTING | Contradicts another prompt |

---

## Inventory

| PROMPT ID | TITLE | PRIMARY PURPOSE | MAJOR REQUIREMENTS | DEPENDENCIES | TEST REQ | DOC REQ | STATUS |
|-----------|-------|-----------------|--------------------|--------------|----------|---------|--------|
| PROMPT-001 (context) | SFO certification objective | Scope: privacy-first local CLI organizer; a series of certification phases + evidence | Local-only, no network, generate supporting docs + verification | None | Yes (tests + gate) | Yes | PARTIALLY FOUND (scoping only) |
| PROMPT-002 | GO-LIVE certification | Production-ready certified maintenance mode verdict | Release gate, test suite, performance, security/privacy, doc set | PROMPT-001 | Yes | Yes | FOUND |
| PROMPT-003 | POST-LAUNCH MONITORING / maintenance governance | Establish maintenance governance mechanism; do NOT re-certify endlessly | Trigger-based validation, change classification, incident register, health review | PROMPT-002 | Targeted only | Yes (3 docs) | FOUND |
| PROMPT-004 | CONTROLLED PRODUCT EVOLUTION / change-impact | Formal process for safely evolving SFO; do NOT invent features | Change classification, impact analysis, validation levels, no new phase | PROMPT-003 | Trigger-based | Yes (3 docs) | FOUND (process-only; no concrete change supplied → STOP applied) |
| PROMPT-005 | MASTER AUDIT | Audit the entire prompt sequence for completeness/consistency/etc. | 53 audit dimensions, prioritized action plan, verdict | All prior | Review | Yes (audit docs) | FOUND (this prompt) |

---

## Prompt Numbering Note

No numeric sequence 1–153 was reproduced in this session. The prompt numbers
referenced by later prompts (e.g. "Prompt 153", "Prompt 155") are **not
independently verifiable** from available context. The visible prompts are the
five above. Earlier phases (per the running objective/context) delivered
30+ documentation artifacts in `docs/` (see `docs/certification-package-index.md`).

## Redundancy Chain (overlaps to be referenced, not duplicated)

- PROMPT-002, PROMPT-003, PROMPT-004 all restate the same governance loop
  (OBSERVE → ... → DOCUMENT / REQUIREMENT → ... → VERIFY).
- Sections repeated verbatim across PROMPT-003/004/005: exception clauses
  ("Do NOT invent features/issues", "stop when objective achieved", "do not
  auto-generate next prompt"). These are **intentional guardrails**, not true
  duplicates — they should be KEPT as contract clauses, not deduplicated.
