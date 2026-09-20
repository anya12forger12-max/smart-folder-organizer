# SFO Incident Lifecycle

**Version:** 0.9.0  
**Status:** Template (no incidents have occurred)  
**Date:** 2026-08-25

---

## Current Reality

**SFO has had zero production incidents.**  
There have been zero releases, zero production deployments, and zero users encountering failures in the field.

This document is a template for future use.

---

## Severity Model

| Level | Definition | Example |
|-------|-----------|---------|
| SEV-1 | Data loss, security breach, widespread failure | File deletion bug, credential exposure |
| SEV-2 | Major functionality broken | Scan fails, recovery fails |
| SEV-3 | Limited functionality issue | Slow on specific filesystem |
| SEV-4 | Minor defect | Typo in help text |

---

## Incident Lifecycle (IF an incident occurs)

```
DETECT → CLASSIFY → CONTAIN → INVESTIGATE → FIX → TEST → REGRESS → RE-CERTIFY → RELEASE → CLOSE
```

---

## What We Actually Do Today

| Step | Tool | Location |
|------|------|----------|
| Detection | pytest failures, release gate | `tests/`, `scripts/release-gate.py` |
| Classification | Severity model above | This document |
| Containment | None needed (local tool) | N/A |
| Investigation | Debug with synthetic files | Manual |
| Fix | Edit source, add regression test | `src/`, `tests/` |
| Regression | pytest run | `python3 -m pytest` |
| Re-certify | Release gate | `scripts/release-gate.py` |
| Release | `python3 -m build` | `dist/` |
| Close | This document | Update status |

---

## One Real Incident (So Far)

**INC-0001: Missing `import os` in database.py** (this session)

- **Detection:** pytest failure (tests expecting `os` module)
- **Root cause:** `os` module not imported after filesystem refactor
- **Fix:** Added `import os` to `database.py:1`
- **Regression:** Covered by existing recovery tests
- **Certification impact:** None (caught in tests before release)
- **Status:** CLOSED

---

## Known Limitations

- No automated incident tracking (single developer, no issue tracker in repo)
- No release history (no versions published)
- No production telemetry (by design)
- Incident lifecycle is manual (appropriate for project scale)

---

## Future Use

When a real incident occurs:

1. Create entry below with unique ID
2. Follow the lifecycle steps
3. Add regression test
4. Run release gate
5. Update this document

---

## Incident Register

| ID | Date | Severity | Component | Root Cause | Fix | Regression Test | Status |
|----|------|----------|-----------|------------|-----|----------------|--------|
| *No incidents recorded* | | | | | | | |
