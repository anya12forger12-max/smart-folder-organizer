# SFO Maintenance Policy

> Version 0.9.0 | Last updated: 2026-08-25

## Change Categories

| Category | Examples |
|----------|----------|
| BUG | Incorrect moves, crash, wrong classification |
| SECURITY | Path bypass, injection, privilege escalation |
| DATA INTEGRITY | Unexpected file modification, lost transaction, false completion |
| COMPATIBILITY | New OS version, filesystem change, Python version |
| DEPENDENCY | Security advisory, abandoned package, breaking change |
| DOCUMENTATION | Incorrect claim, missing procedure, outdated example |

## Change Classification

| Class | When |
|-------|------|
| PATCH | Bug fix, docs fix, test improvement |
| MINOR | New capability, new subcommand, schema addition |
| MAJOR | Architecture change, breaking CLI contract, schema migration |
| SECURITY HOTFIX | Confirmed vulnerability affecting users |
| EMERGENCY HOTFIX | Active data-integrity or exploitation risk |

## Change Intake

Every non-trivial change requires: problem, evidence, risk, security/privacy/compatibility impact, test plan, rollback plan.

## Release Cadence

Release only when there is a concrete reason: bug fix, security fix, dependency update, or validated improvement. Do not release on a calendar.

## Technical Debt

Maintained in `docs/final-closeout-report.md` Section 16. Each item: problem, impact, reason for deferral.

## Architecture Drift

Compare implementation against `docs/final-closeout-report.md` after significant changes. Any divergence must be documented.

## Deprecation

Announce → document replacement → provide migration guidance → remove after deprecation period.
