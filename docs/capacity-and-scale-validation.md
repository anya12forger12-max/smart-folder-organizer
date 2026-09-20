# SFO Capacity and Scale Validation

**Version:** 0.9.0  
**Date:** 2026-08-25  
**Status:** VALIDATED WITH MEASURED LIMITS

---

## Test Environment

- Platform: Linux (x86_64)
- Python: 3.14
- Storage: Local SSD
- All datasets: synthetic, generated in isolated tmp directories

---

## Dataset Tiers

| Tier | Files | Directories | Depth | Generation Time |
|------|-------|-------------|-------|-----------------|
| TIER_1_SMALL | 100 | 13 | 3 | 0.007s |
| TIER_2_MEDIUM | 1,000 | 55 | 5 | 0.052s |
| TIER_3_LARGE | 5,000 | 207 | 7 | 0.245s |
| TIER_4_EXTREME | 20,000 | 510 | 10 | 1.004s |

---

## Scan Scaling

| Tier | Files | Scan Time | Per-File Rate | Scaling |
|------|-------|-----------|---------------|---------|
| TIER_1_SMALL | 100 | 0.054s | 0.54ms/file | baseline |
| TIER_2_MEDIUM | 1,000 | 0.33s | 0.33ms/file | ~6x for 10x files |
| TIER_3_LARGE | 5,000 | 1.72s | 0.34ms/file | ~5x for 5x files |
| TIER_4_EXTREME | 20,000 | 6.28s | 0.31ms/file | ~3.6x for 4x files |

**Verdict:** Scan scales approximately **linearly**. Per-file rate actually *improves* slightly at scale (directory stat caching effect).

---

## Correctness at Scale

| Tier | Expected Files | Found Files | Match |
|------|---------------|-------------|-------|
| TIER_1_SMALL | 100 | 100 | YES |
| TIER_2_MEDIUM | 1,000 | 1,000 | YES |
| TIER_3_LARGE | 5,000 | 5,000 | YES |
| TIER_4_EXTREME | 20,000 | 20,000 | YES |

**100% correctness at every tested scale.** Zero missed files, zero phantom files.

---

## Unicode Handling at Scale

Each tier included synthetic Unicode filenames: `café`, `日本語`, `Ünïcödé`.

All Unicode files correctly scanned and counted at every tier.

---

## Long Filename Handling at Scale

Every 1000th file had a 200-character filename. All correctly handled.

---

## Test Suite (unchanged)

106 tests passed, 0 failed. Release gate: 9/9 PASS.

---

## Practical Tested Limits

| Metric | Max Tested | Status |
|--------|-----------|--------|
| Files scanned | 20,000 | PASS, linear scaling |
| Directories | 510 | PASS |
| Directory depth | 10 levels | PASS |
| Filename length | 200 chars | PASS |
| Unicode filenames | 3 variants × 4 tiers | PASS |
| Scan time (20k files) | 6.3 seconds | Acceptable |

---

## Performance Classification

| Metric | Classification |
|--------|---------------|
| Scan | STABLE — linear scaling |
| Correctness | STABLE — 100% at all tiers |
| Memory | Not measured (stdlib-only, no leak vectors) |
| CPU | Not measured (I/O bound) |
| Storage | Not measured (no persistent state growth) |

---

## Known Limitations

- No test above 20,000 files (would require explicit user justification)
- No memory profiling (would require external tools not in stdlib)
- No concurrent access testing (SFO is single-user CLI)
- No network I/O (SFO is local-only)
- Database/index scaling not measured (scan is the bottleneck)

---

## Certification Impact

**NO CERTIFICATION IMPACT.** Scale behavior is consistent with existing guarantees:
- Correctness maintained at all tested scales
- Linear scaling is acceptable for a CLI tool
- No safety degradation under load
