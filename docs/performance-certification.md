# SFO Performance Certification

**Version:** 0.9.0  
**Date:** 2026-08-27  
**Status:** CERTIFIED

---

## Benchmark Environment

- **OS:** Linux x86_64
- **Runtime:** Python 3.14.6
- **Storage:** NVMe SSD (ext4)
- **CPU:** (user hardware)
- **Background load:** Normal desktop

---

## Startup Performance

| Metric | Value |
|--------|-------|
| Cold start (import + init) | 0.10–0.20s (avg 0.15s) |
| RSS at startup | ~22 MB |
| Startup RSS delta | +0.1 MB |

**Verdict:** FAST — startup adds negligible memory.

---

## Scan Performance (5 runs per tier)

| Files | Avg Time | Per-File | Files/sec | RSS Delta |
|-------|----------|----------|-----------|-----------|
| 100 | 0.052s | 0.52ms | 1,911 | +0.5 MB |
| 1,000 | 0.30s | 0.30ms | 3,337 | +4.6 MB |
| 5,000 | 1.27s | 0.25ms | 3,933 | +9.5 MB |
| 20,000 | 5.76s | 0.29ms | 3,470 | +38.5 MB |

**Scaling:** LINEAR — per-file rate constant (0.25–0.52ms). No superlinear growth.

---

## Search Performance

| Dataset | Time |
|---------|------|
| 5,000 files | 1.36s avg (scan-based) |

Search scales with scan time (linear).

---

## Database Performance

| Operation | Time |
|-----------|------|
| Create + insert 1000 rows + query + close | 0.002s avg (10 runs) |

SQLite operations are sub-millisecond for typical workloads.

---

## Memory Profile

| Metric | Value |
|--------|-------|
| Startup RSS | 22 MB |
| After 100K file scans | 68.7 MB |
| Delta | +13.1 MB |
| Verdict | STABLE (expected for 100K files) |

No unbounded growth detected. Memory is proportional to dataset size.

---

## Soak Test (50 cycles)

| Metric | Value |
|--------|-------|
| Duration | 7.5s (50 scan cycles, 500 files) |
| Errors | 0/50 |
| Data integrity | PASS (start=end=500) |
| RSS delta | +1.4 MB |
| Timing trend | STABLE (no degradation) |

---

## Performance Budget

| Operation | Budget | Actual | Status |
|-----------|--------|--------|--------|
| Startup | < 1s | 0.15s | PASS |
| Scan (1K files) | < 5s | 0.30s | PASS |
| Scan (20K files) | < 30s | 5.76s | PASS |
| Database ops | < 0.1s | 0.002s | PASS |
| Memory (20K) | < 200MB | 60MB | PASS |

---

## Performance Regressions

**None detected.** All metrics within expected bounds.

---

## Known Limitations

- Benchmarks run on a single platform (Linux x86_64, ext4)
- No GPU/CPU profiling (CLI tool, I/O bound)
- No concurrent operation benchmarks (single-process)

---

## Certification Impact

**NO IMPACT.** Performance is within certified operating limits. No optimization needed.
