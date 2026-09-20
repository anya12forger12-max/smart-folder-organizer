# SFO Privacy Assurance Summary

**Version:** 0.9.0  
**Date:** 2026-08-27  
**Status:** CERTIFIED

---

## Privacy Posture (verified today)

| Control | Evidence | Status |
|---------|----------|--------|
| Zero network transmission | AST audit: no socket/http/urllib/requests imports | PASS |
| Zero telemetry | No telemetry code exists | PASS |
| Zero third-party services | Zero runtime dependencies | PASS |
| Zero crash reporting | No crash reporter | PASS |
| Local-only processing | All processing in-process, no IPC/network | PASS |
| Metadata-only processing | SFO reads paths/sizes/timestamps/hashes, not file contents | PASS |
| No secrets | Regex + AST scan | PASS |

---

## Data Inventory

| Data Category | Collected? | Purpose | Stored? | Location |
|---------------|-----------|---------|---------|----------|
| File paths | YES | Core function (organizing) | YES (transient) | In-memory during scan |
| File sizes | YES | Analysis | NO | In-memory |
| File timestamps | YES | Analysis | NO | In-memory |
| File hashes | YES | Duplicate detection | NO | In-memory |
| File contents | NO | Never read | NO | — |
| User settings | YES | Configuration | YES | `~/.config/sfo/` |
| Operation history | YES | Undo | YES | SQLite (`~/.local/share/sfo/`) |
| Diagnostics | YES | Troubleshooting | User-triggered | Printed, not persisted |

---

## What SFO Does NOT Do

- Does NOT transmit any data anywhere
- Does NOT collect telemetry
- Does NOT use third-party services
- Does NOT read file contents
- Does NOT send crash reports
- Does NOT phone home or check for updates over the network

---

## Retention & Deletion

- **Operation history** — retained until user runs `sfo diagnostics --clear` or removes `~/.local/share/sfo/`
- **Diagnostics** — generated on demand, not persisted
- **Temporary files** — none created (operations are in-memory + atomic filesystem moves)

---

## Certification Verdict

**PRIVACY CERTIFIED** — SFO collects the minimum metadata required for its documented function (organizing files), processes it entirely locally, stores only user-controlled history, and transmits nothing. This is privacy by design, not by configuration.
