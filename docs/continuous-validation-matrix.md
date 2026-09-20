# SFO Continuous Validation Matrix

**Version:** 0.9.0  
**Date:** 2026-08-27  

---

**Purpose:** Define the minimum validation required when a concrete change is made to SFO. This prevents both over-certification (running full suites for trivial changes) and under-validation (releasing without tests).

---

| Trigger (change type) | Affected Area | Minimum Validation | Release Requirement |
|----------------------|---------------|-------------------|---------------------|
| Documentation only | Docs | None (review) | Manual review |
| Cosmetics / formatting | Code | None | Manual review |
| Low-risk code (naming, comments) | Local | Targeted test for touched module | Full gate |
| Behavior change | Functional logic | Targeted tests + affected module tests | Full gate |
| Data model change | persistence/schema | Migration tests + full suite | Full gate + recovery |
| Filesystem change | infrastructure/scanning | Filesystem suite + full suite | Full gate |
| Security change | security/ | Adversarial suite + full suite | Full gate + review |
| Privacy change | Any data handling | Privacy review + full suite | Full gate |
| Recovery change | recovery/execution | Recovery drills + full suite | Full gate |
| Platform change | Linux/runtime | Compatibility checks + full suite | Full gate |
| Architecture change | Module boundaries | Full suite + coupling analysis | Full gate |
| Critical change | Anything | All above + release certification | Full gate |

---

## How To Use

1. User reports a concrete change/bug/vulnerability/requirement.
2. Classify it into the **Trigger** column above.
3. Run the **Minimum Validation** — never skip.
4. Optionally run **additional** checks if the change warrants it.
5. Run the release gate before any release.

**Do not** run the entire certification stack for every change. That defeats the purpose of targeted maintenance.

---

## Validation Prerequisites

- `python3 -m pytest` — full suite (106 tests)
- `python3 scripts/release-gate.py` — 9 automated gates
- `PYTHONPATH=src python3` — for AST/secret audits / manual checks

---

## Non-Applicable Triggers

The following DO NOT require revalidation (no such feature exists):
- Backup changes (no backup feature)
- Update/channel changes (no update system)
- Multi-user/auth changes (single-user CLI)
- Telemetry changes (no telemetry)
- Network/storage integration (no network feature)
