# Smart Folder Organizer (SFO)

Privacy-first Linux CLI that organizes your folders **locally** using project
relationships, topics, metadata and your own declarative rules.

SFO **never deletes, never overwrites, and never modifies file contents.**
Every operation is previewed, confirmed, journaled, and reversible.

## Principles

- Local-only: no network access, no telemetry, no accounts.
- Zero dependencies: pure Python standard library, Python >= 3.11.
- Safety-first: mandatory plan validation before any move; durable journals;
  fcntl-based root locking; undo for every completed operation.
- Your rules are data, not code: TOML rule files are parsed, validated, and
  refused if hostile - never interpreted.

## Install

From source (recommended until packaged):

```sh
python3 -m pip install .
```

Requires Python 3.11+ on Linux. No other dependencies.

## Quick start

```sh
sfo preview ~/Downloads          # see what WOULD move - nothing changes
sfo organize ~/Downloads --yes   # do it (journal recorded)
sfo undo                         # restore the previous layout
sfo history                      # audit trail
```

Other commands: `status`, `doctor`, `rules`, `duplicates`, `inspect`,
`protect`, `recover`, `diagnostics`. See `sfo --help`.

## Where SFO keeps its data

| Path | Contents |
|---|---|
| `~/.config/sfo/` | settings.json, rules.toml |
| `~/.local/share/sfo/` | history database, transaction journals, locks |
| `~/.cache/sfo/` | bounded caches |

Uninstalling removes the application; your organized files, configuration,
and history remain yours.

## Development

```sh
python3 -m pytest            # full test suite
python3 -m ruff check src    # lint
scripts/release.py build     # reproducible sdist + wheel
```

## License

MIT - see [LICENSE](LICENSE).
