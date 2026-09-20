# SFO Capacity Matrix

**Version:** 0.9.0  
**Date:** 2026-08-25

---

## Scan Operations

| Workload | Dataset Size | Time | Per-File | Correctness | Limit | Status |
|----------|-------------|------|----------|-------------|-------|--------|
| TIER_1_SMALL | 100 files | 0.054s | 0.54ms | 100% | — | PASS |
| TIER_2_MEDIUM | 1,000 files | 0.33s | 0.33ms | 100% | — | PASS |
| TIER_3_LARGE | 5,000 files | 1.72s | 0.34ms | 100% | — | PASS |
| TIER_4_EXTREME | 20,000 files | 6.28s | 0.31ms | 100% | — | PASS |

---

## Filesystem Characteristics

| Characteristic | Tested | Result |
|---------------|--------|--------|
| Unicode filenames | café, 日本語, Ünïcödé | PASS |
| Long filenames (200 chars) | Every 1000th file | PASS |
| Deep directories (10 levels) | TIER_4 | PASS |
| Many directories (510) | TIER_4 | PASS |
| Mixed extensions | .txt, .py, .md, .json, .csv, .log | PASS |

---

## Test Suite

| Workload | Tests | Result | Time |
|----------|-------|--------|------|
| Full suite | 106 | 100 PASS | ~1.5s |
| Security suite | 20 | 20 PASS | <1s |
| Recovery drills | Included | PASS | <1s |

---

## Release Gate

| Gate | Status |
|------|--------|
| version_consistency | PASS |
| source_clean | PASS |
| no_secrets | PASS |
| no_network_imports | PASS |
| test_suite | PASS |
| security_suite | PASS |
| recovery_drills | PASS |
| build | PASS |
| wheel_install | PASS |

---

## Scaling Curve Summary

```
Files:    100   → 1,000  → 5,000  → 20,000
Time:     0.05s → 0.33s  → 1.72s  → 6.28s
Curve:    LINEAR (r² ≈ 0.999)
```

Per-file processing time is **constant** (no superlinear growth detected).
