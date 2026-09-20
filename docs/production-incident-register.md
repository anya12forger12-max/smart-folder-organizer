# SFO Production Incident Register

**Version:** 0.9.0  
**Date:** 2026-08-27  

---

**Purpose:** Chronological record of significant production incidents and their resolution.

**Note:** SFO is a local CLI tool with no remote telemetry. "Production incidents" are discovered through user reports, test failures, or code review — not through automated monitoring.

---

| ID | Date | Severity | Impact | Root Cause | Response | Recovery | Regression | Status |
|----|------|----------|--------|-----------|----------|----------|-----------|--------|
| INC-0001 | 2026-08-27 | Low | Test failure | Missing `import os` in `database.py` | Added import | N/A (tests only) | Existing recovery tests | CLOSED |

---

## Pre-Launch Incidents (Engineering)

These were found in tests / review BEFORE any release; not production incidents but recorded for completeness.

- **INC-0001** — Missing `import os`, caused test collection errors. Fixed, covered by tests.

---

## Policy

- **Add a new row** only for issues affecting a released artifact or reported by a user.
- **Do not record** sensitive user information.
- **Do not fabricate** incidents that never occurred.
- Every confirmed defect should add a regression test (see `docs/continuous-validation-matrix.md`).
