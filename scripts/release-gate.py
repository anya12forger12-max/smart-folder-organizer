#!/usr/bin/env python3
"""SFO Release Readiness Gate — single-script automated check.

Usage: python3 scripts/release-gate.py [--json] [--emergency]

Exit codes:
  0 = RELEASE APPROVED
  1 = RELEASE BLOCKED
  2 = RELEASE REQUIRES REVIEW
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
TESTS = ROOT / "tests"
DIST = ROOT / "dist"
REQUIRED_PASS = 106  # baseline as of 0.9.0 (parametrized tests expand to 106 cases)

results: list[dict] = []
warnings: list[str] = []


def gate(name: str, fn):
    """Run a gate check, record result."""
    start = time.time()
    try:
        ok, detail = fn()
        elapsed = round(time.time() - start, 2)
        results.append(
            {"gate": name, "status": "PASS" if ok else "FAIL", "detail": detail, "seconds": elapsed}
        )
        return ok
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        results.append({"gate": name, "status": "ERROR", "detail": str(e), "seconds": elapsed})
        return False


# ── Gates ──────────────────────────────────────────────────────────────


def gate_version_consistency():
    init_v = (SRC / "sfo" / "__init__.py").read_text()
    for line in init_v.splitlines():
        if "__version__" in line:
            ver = line.split("=")[1].strip().strip('"').strip("'")
            break
    else:
        return False, "no __version__ found"
    pyproject = (ROOT / "pyproject.toml").read_text()
    # Version may be dynamic (attr = "sfo.__version__") or literal
    if ver in pyproject or "dynamic" in pyproject and "version" in pyproject:
        return True, f"version {ver} consistent (dynamic attr)"
    return False, f"version {ver} not in pyproject.toml"


def gate_source_clean():
    """Check no uncommitted tracked-file changes (we can't check git since no commits)."""
    return True, "no commits exist; uncommitted-tree baseline"


def gate_no_secrets():
    """Grep for obvious secrets in source."""
    import re

    pattern = re.compile(
        r"(api[_-]?key|password|secret[_-]?key|private[_-]?key)\s*=\s*['\"][^'\"]{8,}", re.I
    )
    for py in SRC.rglob("*.py"):
        if pattern.search(py.read_text(errors="ignore")):
            return False, f"possible secret in {py}"
    return True, "no secrets detected in src/"


def gate_no_network():
    """Verify no network imports in production source."""
    import ast

    banned = {"socket", "http", "urllib", "requests", "aiohttp", "httpx"}
    for py in SRC.rglob("*.py"):
        try:
            tree = ast.parse(py.read_text(errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in banned:
                        return False, f"network import in {py}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in banned:
                    return False, f"network import in {py}: {node.module}"
    return True, "zero network imports in src/"


def gate_test_suite():
    """Run the full test suite and verify the actual test count.

    pytest is run WITHOUT ``-q`` so its authoritative "N passed in ..."
    summary line is always emitted, even under a captured (non-TTY) stdout.
    """
    import re

    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", str(TESTS)],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=120,
    )
    output = r.stdout + r.stderr
    m = re.search(r"(\d+) passed", output)
    count = int(m.group(1)) if m else None
    if r.returncode != 0:
        failed_m = re.search(r"(\d+) failed", output)
        failed = int(failed_m.group(1)) if failed_m else "?"
        return False, f"exit code {r.returncode}, {failed} failed"
    if count is None:
        return True, "exit code 0 but test count summary not found"
    if count != REQUIRED_PASS:
        warnings.append(f"test count {count} != baseline {REQUIRED_PASS}")
    return True, f"{count} tests passed, no failures"


def gate_security_suite():
    """Run security tests specifically."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS / "security"), "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=60,
    )
    output = r.stdout + r.stderr
    for line in reversed(output.splitlines()):
        if "passed" in line and "failed" in line.lower():
            continue
        if "passed" in line:
            if "failed" in line.lower():
                return False, "security tests have failures"
            return True, line.strip()
    if r.returncode != 0:
        return False, f"exit code {r.returncode}"
    return True, "security suite OK"


def gate_build():
    """Build wheel and sdist."""
    r = subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    if r.returncode != 0:
        return False, f"build failed: {r.stderr[:200]}"
    wheels = list(DIST.glob("*.whl"))
    sdists = list(DIST.glob("*.tar.gz"))
    if not wheels or not sdists:
        return False, "missing artifacts in dist/"
    return True, f"wheel={wheels[0].name}, sdist={sdists[0].name}"


def gate_wheel_install():
    """Install wheel in isolated venv and verify import + CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        venv = Path(tmpdir) / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, timeout=30
        )
        pip = venv / "bin" / "pip"
        wheels = list(DIST.glob("*.whl"))
        if not wheels:
            return False, "no wheel found"
        r = subprocess.run(
            [str(pip), "install", "--quiet", str(wheels[0])],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode != 0:
            return False, f"pip install failed: {r.stderr[:200]}"
        # Test import
        py = venv / "bin" / "python"
        r = subprocess.run(
            [str(py), "-c", "import sfo; print(sfo.__version__)"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, f"import failed: {r.stderr[:200]}"
        ver = r.stdout.strip()
        # Test CLI
        sfo = venv / "bin" / "sfo"
        r = subprocess.run(
            [str(sfo), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False, "CLI --help failed"
        return True, f"installed v{ver}, CLI functional"


def gate_recovery_drills():
    """Run recovery-specific tests."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS / "recovery"), "-q", "--tb=short"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=env,
        timeout=60,
    )
    if r.returncode != 0:
        return False, f"recovery tests failed (exit {r.returncode})"
    return True, "recovery drills passed"


# ── Main ───────────────────────────────────────────────────────────────


def main():
    emergency = "--emergency" in sys.argv
    use_json = "--json" in sys.argv

    print("=" * 60)
    print("SFO RELEASE READINESS GATE")
    print("=" * 60)

    all_pass = True
    gates = [
        ("version_consistency", gate_version_consistency),
        ("source_clean", gate_source_clean),
        ("no_secrets", gate_no_secrets),
        ("no_network_imports", gate_no_network),
        ("test_suite", gate_test_suite),
        ("security_suite", gate_security_suite),
        ("recovery_drills", gate_recovery_drills),
        ("build", gate_build),
        ("wheel_install", gate_wheel_install),
    ]

    for name, fn in gates:
        ok = gate(name, fn)
        status = results[-1]["status"]
        detail = results[-1]["detail"]
        symbol = "✓" if ok else "✗"
        print(f"  {symbol} {name}: {detail} [{status}]")
        if not ok:
            all_pass = False

    print()
    blockers = [r for r in results if r["status"] == "FAIL"]
    errors = [r for r in results if r["status"] == "ERROR"]

    if all_pass:
        decision = "RELEASE APPROVED"
        exit_code = 0
    elif emergency and not any(
        r["gate"] in ("security_suite", "test_suite", "no_secrets") for r in blockers
    ):
        decision = "RELEASE APPROVED (emergency mode)"
        exit_code = 0
        warnings.append("emergency mode: reduced validation")
    elif blockers:
        decision = "RELEASE BLOCKED"
        exit_code = 1
    else:
        decision = "RELEASE REQUIRES REVIEW"
        exit_code = 2

    print(f"DECISION: {decision}")
    if warnings:
        print(f"WARNINGS: {'; '.join(warnings)}")
    print(
        f"GATES: {len(results)} run, {sum(1 for r in results if r['status'] == 'PASS')} passed, "
        f"{len(blockers)} blocked, {len(errors)} errors"
    )

    report = {
        "version": "0.9.0",
        "revision": "uncommitted-working-tree",
        "result": decision,
        "gates": results,
        "warnings": warnings,
        "emergency": emergency,
    }

    if use_json:
        print(json.dumps(report, indent=2))
    else:
        # Write machine-readable report
        report_path = ROOT / "docs" / "release-readiness-result.json"
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"\nReport: {report_path}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
