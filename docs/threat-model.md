# SFO Threat Model (local, single-user)

## Assets

1. User files anywhere under an organization root (the only thing SFO may
   move, never delete or modify).
2. SFO's own state: journals (`~/.local/share/sfo/journal`), history DB,
   rules, settings — all 0700.

## Trust boundaries

| Boundary | Attacker-controlled inputs |
|---|---|
| Rules file | TOML content: destinations, conditions, priorities |
| Filenames | arbitrary bytes/names incl. control chars, unicode, quotes |
| Filesystem topology | symlinks (incl. escaping dirs), FIFOs, sockets, devices |
| Journal files | tampering, truncation, forged entries |
| Concurrent actors | other processes mutating the tree mid-operation |

## Attacks and mitigations (all test-verified)

| Attack | Mitigation | Tests |
|---|---|---|
| Rule destination escapes root (`../`, absolute, `~`, `;cmd`) | rule validator rejects content; loader refuses whole file; plan containment double-checks | SEC-001..006, CLI hostile-rules |
| Wildcard/glob trickery in rule values | matcher is literal-only string ops | SEC glob-literal case |
| Symlinked dir escaping root during scan | scanner refuses to follow, records ScanError | FS escape case |
| TOCTOU: source swapped to symlink after validation | identity re-check at execution (`require_valid`/preflight) | SEC race cases |
| Forward collision (target exists) | DestinationExistsError, both files intact | SEC, TX |
| Journal tampered to redirect undo outside root | destination containment on undo; refusal | SEC tampered-journal |
| Corrupt/torn journal line | strict parse: mid-file corruption → JournalError; torn final line tolerated as crash artifact | SEC corruption trio |
| Hostile filename breaks journal format | JSON-escaping keeps every line parseable; undo roundtrip works | SEC hostile-filename |
| Chained move (source inside moved dir) | validate_plan refuses | PLN, SEC |
| Protected/ignored files reorganized | protection layer consulted in planning + preflight | CLI protect roundtrip, PLN protected |

## Residual risks (known, accepted for now)

- No defense against a hostile process with the same uid mutating files
  between SFO's check and its rename beyond the identity checks already
  present (kernel-level races are out of scope for a local tool).
- Journals protect integrity but not availability: if state dir is lost,
  undo is impossible (documented behavior).
- GUI/IPC surfaces do not exist yet, so their threat surface is
  intentionally unmodeled until designed.
