"""Session orchestration: one CLI process == one SFO session.

Wires the pipeline together WITHOUT owning any safety logic of its own:
scan -> analyze -> plan are pure reads; execution is delegated to the
Executor (which locks, preflights, journals and verifies). The session's
job is plumbing: configuration, path validation, progress reporting,
history bookkeeping.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from sfo.analysis.engine import AnalysisEngine
from sfo.arrangement.engine import ArrangementEngine
from sfo.config.loader import load_organization_rules, load_user_config
from sfo.config.paths import AppPaths
from sfo.domain.rules import RuleSet
from sfo.errors import SecurityError, SfoError, UsageError
from sfo.execution.engine import ExecutionResult, Executor, new_operation_id
from sfo.infrastructure.filesystem.linux import LinuxFileSystem
from sfo.persistence.database import Database
from sfo.persistence.storage import initialize_storage
from sfo.rules.models import OrganizationRule
from sfo.scanning.scanner import Scanner
from sfo.security.containment import is_within

# Organizing these roots is refused outright. They are system territory;
# no user workflow needs them and a mistake here would be catastrophic.
FORBIDDEN_ROOTS = (
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/proc",
    "/root",
    "/run",
    "/sbin",
    "/sys",
    "/usr",
    "/var",
)


@dataclass(frozen=True)
class PipelineArtifacts:
    root: Path
    scan: object  # ScanResult
    analysis: object  # AnalysisResult
    plan: object  # OrganizationPlan
    user_rules: tuple[OrganizationRule, ...]
    rule_problems: list[str]


class Session:
    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.paths = AppPaths.default().ensure()
        initialize_storage(self.paths)
        self.db = Database(self.paths.database_path)
        self.fs = LinuxFileSystem()
        self.config = load_user_config(self.paths)

    # ------------------------------------------------------------------
    @property
    def ruleset(self) -> RuleSet:
        return self.config.ruleset()

    def organization_rules(self) -> tuple[list[OrganizationRule], list[str]]:
        return load_organization_rules(self.paths)

    # ------------------------------------------------------------------
    def validate_root(self, raw: str) -> Path:
        if not raw or not raw.strip():
            raise UsageError("please provide a folder to organize")
        candidate = Path(raw).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise UsageError(f"folder not found: {raw}") from exc
        except OSError as exc:
            raise UsageError(f"cannot access {raw}: {exc.strerror}") from exc
        if not resolved.is_dir():
            raise UsageError(f"not a folder: {raw}")
        posix = resolved.as_posix()
        for forbidden in FORBIDDEN_ROOTS:
            if posix == forbidden or posix.startswith(forbidden + "/") and forbidden != "/root":
                if posix == forbidden or (forbidden != "/" and posix.startswith(forbidden + "/")):
                    raise SecurityError(
                        f"refusing to organize protected system location: {forbidden}"
                    )
        if not is_within(resolved.parent.parent, resolved):
            # Defensive: resolve() already normalized; kept as belt-and-braces.
            raise SecurityError("path could not be normalized safely")
        return resolved

    # ------------------------------------------------------------------
    def run_pipeline(
        self,
        root: Path,
        progress=None,  # Callable[[str], None] | None
        cancelled=None,  # Callable[[], bool] | None
    ) -> PipelineArtifacts:
        ruleset = self.ruleset
        user_rules, problems = self.organization_rules()

        if cancelled is not None and cancelled():
            raise SfoError("cancelled before scanning")

        def scan_progress(count: int) -> None:
            if progress:
                progress(f"Scanning… {count} entries")

        scanner = Scanner(
            self.fs,
            ruleset,
            hash_files=False,
            progress=scan_progress,
            cancelled=cancelled,
        )
        scan = scanner.scan(root)

        if progress:
            progress("Analyzing relationships…")
        analysis = AnalysisEngine(self.fs).analyze(scan)

        if progress:
            progress("Planning…")
        engine = ArrangementEngine(self.fs)
        plan = engine.build_plan(scan, analysis, ruleset, user_rules=tuple(user_rules))

        return PipelineArtifacts(
            root=root,
            scan=scan,
            analysis=analysis,
            plan=plan,
            user_rules=tuple(user_rules),
            rule_problems=problems,
        )

    # ------------------------------------------------------------------
    def execute_plan(self, artifacts: PipelineArtifacts) -> ExecutionResult:
        plan = artifacts.plan
        operation_id = new_operation_id()
        txn_id = self.db.record_transaction(
            kind="ORGANIZE",
            root=plan.root,
            plan_fingerprint=f"{plan.source_snapshot}:{plan.statistics.moves}",
            external_id=operation_id,
        )
        self.db.set_transaction_status(txn_id, "EXECUTING")
        executor = Executor(self.fs, self.paths.data_dir)
        try:
            result = executor.execute(plan, self.ruleset, operation_id=operation_id)
        except Exception:
            self.db.set_transaction_status(txn_id, "INTERRUPTED")
            raise

        status_map = {
            "COMPLETED": "COMPLETED",
            "PARTIAL": "PARTIAL",
            "FAILED": "FAILED",
        }
        self.db.set_transaction_status(txn_id, status_map[result.status.value])

        seq = 0
        for action in plan.moves:
            seq += 1
            failure = next((f for f in result.failures if f.action_id == action.action_id), None)
            moved = failure is None
            self.db.record_operation(
                txn_id=txn_id,
                seq=seq,
                op_kind="MOVE",
                source=action.source,
                destination=action.destination,
                expected_identity=action.file_identity.to_json() if action.file_identity else None,
                result_identity=None,
                status=("VERIFIED" if moved else f"FAILED:{failure.reason_code}"),
                error=(failure.message if failure else None),
            )
        return result

    # ------------------------------------------------------------------
    def pending_recoveries(self):
        from sfo.recovery.reconciliation import pending_recoveries

        return pending_recoveries(self.paths.data_dir, self.fs)

    def stdout_note(self, message: str) -> None:
        if self.verbose:
            print(message, file=sys.stderr)
