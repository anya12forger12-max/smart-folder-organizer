#!/usr/bin/env bash
# install.sh — one-command installer for this repository.
# Auto-detects the project stack and installs dependencies into an isolated
# environment. Safe to re-run.

set -euo pipefail

BOLD="\033[1m"; GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"; RESET="\033[0m"
info(){ echo -e "${BOLD}${GREEN}[+]${RESET} $*"; }
warn(){ echo -e "${BOLD}${YELLOW}[!]${RESET} $*"; }
err(){ echo -e "${BOLD}${RED}[x]${RESET} $*" >&2; }
die(){ err "$*"; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# ---- Flutter ----
if [ -f "pubspec.yaml" ]; then
    command -v flutter >/dev/null 2>&1 || die "Flutter SDK not found. Install from https://docs.flutter.dev/get-started/install"
    info "Flutter project detected — running flutter pub get"
    flutter pub get
    info "Done. Run: flutter run"
    exit 0
fi

# ---- Node (pnpm workspace) ----
if [ -f "pnpm-workspace.yaml" ] || [ -f "pnpm-workspace.yml" ]; then
    if command -v pnpm >/dev/null 2>&1; then
        info "pnpm workspace detected — running pnpm install"
        pnpm install
    else
        die "pnpm not found. Install: npm i -g pnpm"
    fi
    info "Done."
    exit 0
fi

# ---- Node (npm) ----
if [ -f "package.json" ]; then
    if command -v npm >/dev/null 2>&1; then
        info "Node project detected — running npm install"
        npm install
    else
        die "npm not found. Install Node.js from https://nodejs.org"
    fi
    info "Done. Check package.json scripts for build/test commands."
    exit 0
fi

# ---- .NET ----
if ls *.sln >/dev/null 2>&1; then
    command -v dotnet >/dev/null 2>&1 || die ".NET SDK not found. Install .NET 8+ from https://dotnet.microsoft.com"
    info ".NET solution detected — running dotnet restore"
    dotnet restore
    info "Done. Run: dotnet build"
    exit 0
fi

# ---- Python ----
if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
    PY=""
    for c in python3 python; do
        if command -v "$c" >/dev/null 2>&1; then PY="$(command -v "$c")"; break; fi
    done
    [ -n "$PY" ] || die "Python 3 not found."
    info "Python project detected — creating virtual environment"
    if [ ! -d ".venv" ]; then
        "$PY" -m venv .venv
    fi
    VENV_PY="$ROOT/.venv/bin/python"
    VENV_PIP="$ROOT/.venv/bin/pip"
    "$VENV_PIP" install --upgrade pip >/dev/null 2>&1 || true
    if [ -f "pyproject.toml" ]; then
        info "Installing package (pip install .)"
        "$VENV_PIP" install -q .
    elif [ -f "requirements.txt" ]; then
        info "Installing requirements.txt"
        "$VENV_PIP" install -q -r requirements.txt
    fi
    if [ -f "requirements-dev.txt" ]; then
        info "Installing dev requirements"
        "$VENV_PIP" install -q -r requirements-dev.txt || true
    fi
    info "Done. Activate with: source .venv/bin/activate"
    exit 0
fi

die "No recognised project manifest found (pubspec.yaml, package.json, *.sln, pyproject.toml, requirements.txt)."
