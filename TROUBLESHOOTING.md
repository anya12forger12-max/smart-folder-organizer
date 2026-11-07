# Troubleshooting

## Installation

- **`./install.sh` fails** — ensure prerequisites (Flutter/Node/Python/.NET) are
  installed and on PATH. Re-run after installing.
- **Permission denied** — `chmod +x install.sh`.
- **Network errors** — check connectivity/proxy; retry.

## Runtime

- **App won't start** — check logs; verify `.env`/config files are present
  (copy from `.env.example`).
- **Tests fail locally but pass in CI** — ensure dependency versions match
  (use the lockfile).

## Getting help

Open an issue with reproduction steps, environment details, and logs.
