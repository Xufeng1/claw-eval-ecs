import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

from eve_ecs_runner.base_executor import BaseExecutor
from eve_ecs_runner.eve_result import EveResult, JudgeDetail

from .config import ClawEvalConfig

# Use the claw-eval binary from the same venv as the running Python.
_CLAW_EVAL = str(Path(sys.executable).parent / "claw-eval")


def _deep_merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


logger = logging.getLogger(__name__)


class ClawEvalExecutor(BaseExecutor):
    _DEFAULT_TRACE_DIR = "claw_traces"

    def __init__(self, config: ClawEvalConfig):
        super().__init__(config)
        self.config: ClawEvalConfig = config
        self.trace_dir = self._parse_trace_dir()

    def run_inference(self):
        raise NotImplementedError(
            "Use run_all(); claw-eval batch handles inference and grading together."
        )

    def run_evaluation(self):
        raise NotImplementedError(
            "Use run_all(); claw-eval batch handles inference and grading together."
        )

    def run_all(self):
        try:
            self._run_batch()
            self._resolve_trace_dir()
            results = self.to_eve_format()
            self._write_eve_file(results)
        except Exception as e:
            self.generate_error_report(str(e))
            raise

    def _resolve_trace_dir(self):
        """Locate the actual trace output directory created by claw-eval.

        claw-eval batch creates a timestamped subdirectory under
        --trace-dir (e.g. model_26-03-31-12-00/).  Since each run
        uses a fresh ECS instance there is exactly one such directory.
        """
        subdirs = [p for p in self.trace_dir.iterdir() if p.is_dir()]
        if len(subdirs) == 1:
            self.trace_dir = subdirs[0]
            logger.info("Resolved trace dir: %s", self.trace_dir)
        elif len(subdirs) > 1:
            # Shouldn't happen on a fresh ECS, but pick the newest just in case.
            self.trace_dir = max(subdirs, key=lambda p: p.stat().st_mtime)
            logger.warning("Multiple trace subdirs found, using newest: %s", self.trace_dir)

    def _parse_trace_dir(self) -> Path:
        """Extract --trace-dir from extra_args, or use the default."""
        args = self.config.extra_args
        for i, arg in enumerate(args):
            if arg == "--trace-dir" and i + 1 < len(args):
                return Path(args[i + 1]).resolve()
        return self.config.work_dir / self._DEFAULT_TRACE_DIR

    def _apply_config_override(self, extra: list[str]) -> list[str]:
        """If CONFIG_OVERRIDE env var is set, merge it into the base config."""
        override_json = os.environ.get("CONFIG_OVERRIDE")
        if not override_json:
            return extra

        config_path = None
        config_idx = None
        for i, arg in enumerate(extra):
            if arg == "--config" and i + 1 < len(extra):
                config_path = Path(extra[i + 1])
                config_idx = i + 1
                break

        if config_path is None:
            logger.warning("CONFIG_OVERRIDE is set but no --config found in args; ignoring")
            return extra

        if not config_path.is_absolute():
            config_path = self.config.work_dir / config_path

        override = json.loads(override_json)
        with open(config_path, "r", encoding="utf-8") as f:
            base = yaml.safe_load(f) or {}
        _deep_merge(base, override)

        merged_path = config_path.parent / "config_merged.yaml"
        with open(merged_path, "w", encoding="utf-8") as f:
            yaml.dump(base, f, default_flow_style=False)

        logger.info("Merged CONFIG_OVERRIDE into %s -> %s", config_path, merged_path)

        extra = list(extra)
        extra[config_idx] = str(merged_path)
        return extra

    def _run_batch(self):
        if self.trace_dir.exists():
            shutil.rmtree(self.trace_dir)
        self.trace_dir.mkdir(parents=True)

        # Build command: extra_args is the single source of truth for
        # claw-eval flags.  Only inject defaults for args not already present.
        extra = list(self.config.extra_args)
        extra = self._apply_config_override(extra)
        if "--trace-dir" not in extra:
            extra = ["--trace-dir", str(self.trace_dir)] + extra
        if "--sandbox" not in extra:
            extra = ["--sandbox"] + extra
        if "--trials" not in extra:
            extra = ["--trials", "3"] + extra

        cmd = [_CLAW_EVAL, "batch"] + extra

        logger.info("Running claw-eval batch: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                cwd=self.config.work_dir,
                check=True,
                text=True,
                capture_output=True,
            )
            if result.stdout:
                logger.info("claw-eval stdout:\n%s", result.stdout.rstrip())
            logger.info("claw-eval batch completed successfully")
        except subprocess.CalledProcessError as e:
            logger.error("claw-eval batch failed (exit code %s)", e.returncode)
            if e.stdout:
                logger.error("stdout:\n%s", e.stdout.rstrip())
            if e.stderr:
                logger.error("stderr:\n%s", e.stderr.rstrip())
            raise RuntimeError(
                f"claw-eval batch failed (exit code {e.returncode}):\n"
                f"{(e.stderr or e.stdout or '').rstrip()}"
            ) from e

    def to_eve_format(self) -> EveResult:
        summary_path = self.trace_dir / "batch_summary.json"
        results_path = self.trace_dir / "batch_results.json"

        missing = [p.name for p in (summary_path, results_path) if not p.exists()]
        if missing:
            raise FileNotFoundError(f"Missing claw-eval output files: {', '.join(missing)}")

        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        with open(results_path, "r", encoding="utf-8") as f:
            results = json.load(f)

        details = []
        judge_details = []

        for idx, task_res in enumerate(results):
            task_id = task_res.get("task_id", f"task_{idx}")
            task_name = task_res.get("task_name", "")

            is_passed = task_res.get("avg_passed", False)
            avg_score = task_res.get("avg_score", 0.0)

            details.append(
                {
                    "idx": idx,
                    "instance_id": task_id,
                    "instance_name": task_name,
                    "correct": is_passed,
                    "score": round(avg_score * 100, 2),
                }
            )

            all_trials = task_res.get("trials", [])
            total_wall_time = sum(t.get("wall_time_s", 0) for t in all_trials)
            total_tokens = sum(t.get("tokens", 0) for t in all_trials)
            first_trial = all_trials[0] if all_trials else {}

            judge_details.append(
                JudgeDetail(
                    idx=idx,
                    prompt=task_name,
                    origin_prompt=task_name,
                    origin_prompt_hash="",
                    origin_prediction=[],
                    processed_prediction=[],
                    reference="",
                    correct=is_passed,
                    is_multiturn=True,
                    ext_info={
                        "instance_id": task_id,
                        "score": avg_score,
                        "time_costs": round(total_wall_time, 2),
                        "tokens": total_tokens,
                        "task_name": task_name,
                        "difficulty": task_res.get("difficulty"),
                        "error": task_res.get("error"),
                        "pass_at_1": task_res.get("pass_at_1"),
                        "pass_hat_k": task_res.get("pass_hat_k"),
                        "sub_scores": {
                            "completion": first_trial.get("completion"),
                            "robustness": first_trial.get("robustness"),
                            "communication": first_trial.get("communication"),
                            "safety": first_trial.get("safety"),
                        },
                        "trials_detail": all_trials,
                    },
                )
            )

        k = summary.get("trials_per_task", 1)
        total = summary.get("tasks", 0) or 0
        judge_ratio = len(judge_details) / total if total else 0.0
        return EveResult(
            score=round(summary.get("avg_score", 0.0) * 100, 2),
            judge_ratio=judge_ratio,
            report={
                "total_instances": summary.get("tasks"),
                "resolved_instances": summary.get(f"pass_at_{k}"),
                "trials_per_task": k,
                "metrics": {
                    "pass_at_k": summary.get(f"pass_at_{k}"),
                    "pass_hat_k": summary.get(f"pass_hat_{k}"),
                    "avg_score": summary.get("avg_score"),
                },
                "resource_usage": {
                    "total_tokens": summary.get("total_tokens"),
                    "model_input_tokens": summary.get("total_input_tokens"),
                    "model_output_tokens": summary.get("total_output_tokens"),
                    "total_wall_time_s": summary.get("total_wall_time_s"),
                    "total_model_time_s": summary.get("total_model_time_s"),
                },
            },
            details=details,
            judge_details=judge_details,
            detail_oss_url=f"{self.config.oss_bucket}/results.tgz",
            metadata={
                "benchmark": "claw-eval",
                "run_id": self.config.run_id,
                "timestamp": datetime.now().isoformat(),
                "artifacts": [
                    f"{self.config.oss_bucket}/results.tgz",
                ],
            },
        )

    def get_artifacts(self) -> list:
        return [self.trace_dir]
