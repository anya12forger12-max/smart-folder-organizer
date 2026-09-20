# SFO Master Gap Matrix

> **Version:** 0.9.0 | **Audit Date:** 2026-08-27
>
> GAPS are found and recorded. Per NO-INVENTION rule, a "gap" is only flagged
> when the architecture/evidence supports it — not because another project
> "might" have that feature.

| GAP ID | AREA | MISSING REQUIREMENT / ISSUE | RISK | DEPENDENCY | RECOMMENDED ACTION | STATUS |
|--------|------|------------------------------|------|-----------|--------------------|--------|
| GAP-001 | Release/Test accuracy | Release-gate `test_suite` used a **dot-count heuristic** (`output.count(".")`) that was unreliable in captured (non-TTY) mode — it could not actually confirm the test count it reported. Baseline 106 was CORRECT (parametrized tests expand 94 functions to 106 cases). | **P2 (Medium, now FIXED)** — heuristic could misreport count; no functional impact | none | **FIXED** — gate now parses pytest's authoritative "N passed" summary; verified reports "106 tests passed". See `master-traceability-matrix.md` correction note | CLOSED |
| GAP-002 | Documentation | No **architecture/design doc** tracing module boundaries (analysis, arrangement, execution, persistence, undo, recovery) | **P2 (Medium)** — traceability of architecture changes weakened | implies many modules | Create `docs/architecture.md` only if maintainability review deems it required (it is) | OPEN |
| GAP-003 | Installation/upgrade/uninstall | No dedicated doc; only README + gate `wheel_install`. Upgrade/uninstall paths unverified in docs | **P2 (Medium)** | build | If productionized, add install/upgrade/uninstall doc; today release gate covers install only | OPEN |
| GAP-004 | Backup | Earlier phases referenced "backup" but SFO has **no backup feature** — journaling is the data-safety mechanism only | **P1 (High if claimed)** — must not falsely certify backup capability that does not exist | honesty rule | Document explicitly: no backup feature; recovery = journal + non-destructive design. Not a code gap, a **certification-accuracy** gap | OPEN (doc-only) |
| GAP-005 | Concurrency | Zero concurrent mechanisms — correctly N/A. No gap; must not be flagged as missing | n/a | n/a | Keep documented as limitation; do NOT add concurrency | CLOSED (correctly N/A) |
| GAP-006 | CI/CD | No automated CI; gate is manual | **P3 (Low)** — not required for local CLI; tracked TD-003 | none | Optional improvement only | OPEN (debt) |
| GAP-007 | Performance regression automation | No automated performance baseline check; only one-off benchmarks | **P3 (Low)** | none | Optional; add only if performance becomes a validated requirement | OPEN (optional) |

## NON-GAPS (explicitly: do NOT "fix" these — NO-INVENTION rule)
- **No telemetry / no remote monitoring** — SFO has no network; observability is local logs/health model only. This is correct, not a gap.
- **No authentication/authorization** — single-user local CLI. Correct, not a gap.
- **No auto-update** — local tool; not a gap.
- **No multi-user / multi-worker** — single-process. Correct.
