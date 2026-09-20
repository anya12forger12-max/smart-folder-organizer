# SFO Terminology Audit

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27

## Findings

A scan of `src/` for the key domain terms shows **consistent single-name usage
— no aliasing conflicts.**

| Concept | Canonical term(s) | Alternate names found | Verdict |
|---------|-------------------|----------------------|---------|
| An operation to execute | `organize` / `cmd_organize` | none conflicting | Consistent |
| Read-only dry-run | `preview` / `cmd_preview` | none | Consistent |
| Non-destructive recovery | `recover` / `cmd_recover` | none | Consistent |
| Durable transaction log | `journal` / `TransactionJournal` | none | Consistent |
| Reverse of operations | `undo` / `cmd_undo` | none | Consistent |
| Partial operation state | `OpStatus.PARTIAL` | none | Consistent |
| Root-level file lock | `RootLock` | "lock" (generic) | Consistent (generic usage is fine) |

## Terminology notes

- **"Recovery"** is used in two senses across docs: (a) report-only recovery of
  interrupted operations (the SFO feature), and (b) generic disaster recovery.
  Where docs discuss "backup & DR" they mean journal-based data safety, NOT a
  backup feature. This is the source of CON-002 — worth standardizing to
  avoid implying a non-existent backup capability.

- **"Certification"** is used per-phase and as the overall state; no conflict.

## Recommended standardization
1. Use **"journal-based recovery"** (or "data-safety") instead of bare
   "backup" in docs when no backup feature exists.
2. Standardize **"production operation"** for the terminal-state verdict
   wording across PROMPT-003/004/005.

No terminology renames required in code.
