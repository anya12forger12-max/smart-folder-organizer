# SFO Recovery Decision Tree

**Version:** 0.9.0  
**Date:** 2026-08-27

---

## Decision Tree

```
SFO operation failed or reported error
  │
  ├─ Exit code != 0?
  │   ├─ YES → Check stderr message
  │   │   ├─ "folder not found" → User error: verify path
  │   │   ├─ "read-only" → Permission error: check permissions
  │   │   ├─ "database" → Database error → go to DATABASE FAILURE
  │   │   └─ Other → See error message for guidance
  │   └─ NO → Operation succeeded
  │
  ├─ DATABASE FAILURE
  │   ├─ Is index.db accessible?
  │   │   ├─ YES → Run `sfo recover`
  │   │   │   ├─ Recovery succeeds → Verify with `sfo doctor`
  │   │   │   └─ Recovery fails → Manual: delete index.db, rescan
  │   │   └─ NO → Filesystem issue: check permissions, disk space
  │
  ├─ INTERRUPTED OPERATION (Ctrl+C, kill, crash)
  │   ├─ Run `sfo recover`
  │   │   ├─ Detects interrupted op → Offers recovery → Accept
  │   │   │   └─ Verify with `sfo doctor`
  │   │   └─ No interrupted ops → State is clean, resume normally
  │   └─ If recover fails → Delete journal files, rescan
  │
  ├─ FILE SYSTEM INCONSISTENCY
  │   ├─ Run `sfo doctor`
  │   │   ├─ Reports issues → Follow recommendations
  │   │   └─ Reports clean → Problem may be external to SFO
  │   └─ If files moved outside SFO → Rescan to update index
  │
  └─ UNKNOWN STATE
      ├─ Run `sfo doctor` → Diagnostic output
      ├─ Run `sfo diagnostics` → Full diagnostic summary
      └─ If still unclear → Manual investigation needed
```

---

## Recovery Commands

| Situation | Command |
|-----------|---------|
| Interrupted operation | `sfo recover` |
| Health check | `sfo doctor` |
| Full diagnostics | `sfo diagnostics` |
| Clear stale state | `sfo diagnostics --clear` |
| Nuclear option | Delete `~/.local/share/sfo/` and rescan |

---

## What Cannot Be Recovered

- Files moved outside SFO after SFO moved them (SFO doesn't track external moves)
- Deleted source files (SFO never deletes, only moves)
- Configuration changes made manually

---

## RPO / RTO

| Metric | Value | Notes |
|--------|-------|-------|
| RPO | Last completed operation | SFO journals each operation; interrupted ops can be recovered |
| RTO | < 1 second | `sfo recover` replays journal instantly |

These are not formal SLAs — SFO is a local CLI tool, not a service.
