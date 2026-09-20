# SFO Maintainability and Code Quality Scorecard

**Version:** 0.9.0  
**Date:** 2026-08-25  
**Source modules:** 81 Python files  
**Test files:** 13  

---

## Architecture

| Package | Purpose | Dependencies |
|---------|---------|-------------|
| cli | User interface, command routing | everything (expected) |
| config | Settings, paths, rules loading | domain, errors, security |
| scanning | Filesystem scan | domain, errors, infrastructure, security |
| analysis | Project/topic relationship detection | domain, infrastructure, scanning |
| rules | Rule parsing and matching | domain, errors |
| planning | Move plan generation | domain, errors, infrastructure |
| execution | File operations with journal | domain, errors, infrastructure, planning |
| persistence | SQLite database | config, errors, security |
| recovery | Transaction recovery | execution, infrastructure |
| undo | Revert operations | domain, errors, execution, infrastructure, persistence |
| duplicates | Duplicate detection | domain, infrastructure |
| inspection | File/folder inspection | domain, duplicates, rules |
| security | Containment, permissions | errors |
| infrastructure | Filesystem abstraction | domain, errors, scanning |
| domain | Core types and models | (none — leaf) |

**Coupling verdict:** Clean layered architecture. Domain is a leaf. Security depends only on errors. No circular imports.

---

## Largest Modules (maintainability risk)

| Module | Lines | Risk |
|--------|-------|------|
| `cli/commands.py` | 843 | Highest complexity — command routing + all user workflows |
| `inspection/inspector.py` | 534 | Large but cohesive |
| `arrangement/engine.py` | 418 | Arrangement logic |
| `scanning/scanner.py` | 325 | Core scan |
| `duplicates/scanner.py` | 247 | Duplicate detection |
| `execution/journal.py` | 214 | Transaction journal |
| `rules/parser.py` | 213 | Rule parsing |
| `cli/app.py` | 210 | CLI entry point |

**`commands.py` at 843 lines is the primary maintainability risk.** All user commands route through this single module. Splitting into per-command modules would improve maintainability.

---

## Error Model

18 named error types extending `SfoError`. Consistent hierarchy. Each error maps to a specific failure mode. Good.

---

## Test Coverage

| Area | Tests | Status |
|------|-------|--------|
| cli | 21 tests | PASS |
| security | 20 tests | PASS |
| duplicates | 15 tests | PASS |
| inspection | 16 tests | PASS |
| observability | 8 tests | PASS |
| planning | 9 tests | PASS |
| recovery | 3 tests | PASS |
| rules | 8 tests | PASS |
| undo | 6 tests | PASS |
| **Total** | **106 tests** | **ALL PASS** |

**Untested critical areas:** execution, persistence, infrastructure, scanning, config. These are exercised indirectly through cli/integration tests but lack dedicated unit tests.

---

## CI/CD

**None.** No GitHub Actions, no pre-commit hooks. Builds are manual. This is the largest maintainability gap.

---

## Technical Debt Register

| ID | Area | Description | Priority |
|----|------|-------------|----------|
| TD-001 | Architecture | `commands.py` at 843 lines — all commands in one module | Medium |
| TD-002 | Testing | No dedicated tests for execution, persistence, infrastructure, scanning | Medium |
| TD-003 | CI/CD | No automated CI pipeline | High |
| TD-004 | Documentation | No CONTRIBUTING.md or developer setup guide | Low |
| TD-005 | Testing | No test coverage measurement tooling | Low |

---

## Build Reproducibility

`python3 -m build --no-isolation` produces deterministic wheel + sdist. Verified. No generated code in repo.

---

## Maintainability Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| Architecture | GOOD | Clean layering, no circular deps |
| Cohesion | GOOD | Each module has clear purpose |
| Coupling | GOOD | Minimal cross-package deps (except cli) |
| Complexity | ACCEPTABLE | `commands.py` is the main risk |
| Testability | GOOD | Domain logic is testable without I/O |
| Test quality | GOOD | Tests verify behavior, not implementation |
| Test coverage | PARTIAL | 106 tests, critical gaps in persistence/execution |
| Documentation | PARTIAL | User docs good, developer docs missing |
| Dependencies | EXCELLENT | Zero runtime dependencies |
| Build | GOOD | Reproducible wheel builds |
| Debuggability | GOOD | `--debug` flag, structured error types |
| CI/CD | POOR | No automated pipeline |
| Technical debt | LOW | 5 tracked items, none critical |

---

## Known Limitations

- No CI/CD pipeline (largest gap)
- `commands.py` is the most complex single file (843 lines)
- 8 modules lack dedicated unit tests (covered by integration tests)
- No CONTRIBUTING.md for new developer onboarding
- No automated coverage measurement

---

## Certification Impact

**NO CERTIFICATION IMPACT.** Code quality is sufficient for maintenance mode. The identified debt items are improvements, not blockers.
