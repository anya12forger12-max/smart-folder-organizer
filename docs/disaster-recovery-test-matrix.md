# SFO Disaster Recovery Test Matrix

**Version:** 0.9.0  
**Date:** 2026-08-27

---

| Failure | Detection | Safe State | Recovery Method | Expected Result | Tested | Status |
|---------|-----------|-----------|-----------------|-----------------|--------|--------|
| Application crash mid-op | `sfo recover` detects journal | Interrupted op marked | Journal replay | Op completes or rolls back | `tests/recovery/test_drill.py` | PASS |
| Database corruption | `sfo doctor` / error | Read-only mode | Delete index.db, rescan | Index rebuilt from filesystem | Manual | PASS |
| Index corruption | `sfo doctor` | No index lookup | Rebuild from filesystem | Correct index | Manual | PASS |
| Interrupted transaction | `sfo recover` | Transaction state preserved | Journal replay | Safe completion/rollback | `test_drill.py` | PASS |
| Invalid configuration | Startup error | Refuse to start | Fix config | Clean startup | `tests/cli/` | PASS |
| Read-only filesystem | Error message | Operation blocked | Fix permissions | Operation succeeds | `test_commands.py` | PASS |
| Low storage | Error message | Operation blocked | Free space | Retry succeeds | Manual | PASS |

---

## Recovery Proof Points

1. **Journal-based recovery** — every operation writes a journal before execution; on interrupt, `sfo recover` knows the exact state.
2. **Filesystem is source of truth** — index is always derived; can be rebuilt from any known-good filesystem state.
3. **No destructive defaults** — SFO never deletes; it only moves and journals, so "missing" data is always traceable.
4. **Near-zero RTO** — `sfo recover` completes in milliseconds.

---

## Known Limitations

- No automated backup/restore (SFO doesn't have a backup feature)
- No cross-machine state transfer
- External filesystem moves by other tools aren't tracked
- If the entire filesystem is lost AND no external copy of moved data exists, those files are lost (SFO has no built-in backup)
