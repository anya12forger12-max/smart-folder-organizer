# SFO Operational Health Model

**Version:** 0.9.0  
**Status:** Honest, minimal, applicable  
**Date:** 2026-08-25

---

## Why This Document Is Short

SFO is a **local CLI tool** with:
- Zero network communication
- Zero telemetry
- Zero server-side infrastructure
- Zero background processes

There is no "production infrastructure" to monitor. The monitoring model is:
**exit codes, error messages, and the release gate script.**

---

## Actual Health Model

| Component | Health Signal | Normal State | Failure Indicator |
|-----------|--------------|--------------|-------------------|
| Startup | Exit code | 0 | Non-zero exit |
| Database | SQLite errors | No errors | `sqlite3.OperationalError` |
| Index | File presence | `index.db` exists | Missing or corrupt file |
| Filesystem | `OSError` / permission | No errors | stderr message + non-zero exit |
| Transaction | Atomic write | Complete | Partial file + recovery prompt |
| Recovery | Restore capability | Working | stderr message |
| Tests | pytest exit | 0 failures | Non-zero exit |

---

## Error Communication (Already Implemented)

SFO already communicates errors via:
- **stderr messages** — human-readable descriptions
- **Exit codes** — machine-readable status
- **`sfo recover`** — explicit recovery command

This IS the monitoring system. No additional infrastructure is needed.

---

## What Does NOT Apply

| Requested Feature | Why It Does Not Apply |
|-------------------|-----------------------|
| Telemetry | SFO collects zero data |
| Health dashboards | No server to monitor |
| Alert rules | No background process |
| Incident correlation | Failures are local, one-at-a-time |
| Rollback triggers | No prior release exists |
| Crash reporting | User runs CLI manually |
| Resource monitoring | User manages their own system |

---

## What IS Useful (Already Implemented)

| Tool | Purpose | Location |
|------|---------|----------|
| `scripts/release-gate.py` | Automated release readiness | 9 gates, machine-readable JSON |
| `pytest` test suite | 106 regression tests | `tests/` |
| Security suite | 20 security validations | `tests/security/` |
| `sfo recover` | Transaction recovery | Built-in CLI command |

---

## Privacy Status

**No user data is collected, stored, transmitted, or processed outside the user's own machine.**

This is not a monitoring claim — it is a design fact verified by:
- Code audit: zero network imports in `src/`
- Test suite: privacy tests pass
- Architecture: stdlib-only, no dependencies

---

## Known Limitations

- No automated crash reporting (user must report issues manually)
- No remote health visibility (by design)
- No background health checks (user runs CLI on demand)
- No structured logging (not needed for a CLI tool)

These are not gaps. They are correct design choices for a local-first privacy tool.
