import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from eve_ecs_runner.benchmarks.claw_eval.config import ClawEvalConfig
from eve_ecs_runner.benchmarks.claw_eval.executor import ClawEvalExecutor, _deep_merge


SAMPLE_SUMMARY = {
    "tasks": 3,
    "trials_per_task": 1,
    "pass_at_1": 2,
    "pass_hat_1": 2,
    "avg_score": 0.75,
    "total_tokens": 1000,
    "total_input_tokens": 600,
    "total_output_tokens": 400,
    "total_wall_time_s": 120.0,
    "total_model_time_s": 80.0,
}

SAMPLE_RESULTS = [
    {
        "task_id": "task-1",
        "task_name": "Test Task 1",
        "avg_passed": True,
        "avg_score": 1.0,
        "difficulty": "easy",
        "pass_at_1": 1.0,
        "pass_hat_k": 1.0,
        "trials": [{"wall_time_s": 30, "tokens": 300, "completion": 1.0}],
    },
    {
        "task_id": "task-2",
        "task_name": "Test Task 2",
        "avg_passed": True,
        "avg_score": 0.8,
        "difficulty": "medium",
        "trials": [{"wall_time_s": 40, "tokens": 400}],
    },
    {
        "task_id": "task-3",
        "task_name": "Test Task 3",
        "avg_passed": False,
        "avg_score": 0.0,
        "difficulty": "hard",
        "error": "timeout",
        "trials": [{"wall_time_s": 50, "tokens": 300}],
    },
]


class TestToEveFormat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.trace_dir = Path(self.tmp) / "traces" / "model_run"
        self.trace_dir.mkdir(parents=True)

        with open(self.trace_dir / "batch_summary.json", "w") as f:
            json.dump(SAMPLE_SUMMARY, f)
        with open(self.trace_dir / "batch_results.json", "w") as f:
            json.dump(SAMPLE_RESULTS, f)

        self.config = ClawEvalConfig(run_id="test-run", work_dir=Path(self.tmp))
        self.executor = ClawEvalExecutor(self.config)
        self.executor.trace_dir = self.trace_dir

    def test_score(self):
        result = self.executor.to_eve_format()
        self.assertEqual(result.score, 75.0)

    def test_judge_ratio(self):
        result = self.executor.to_eve_format()
        self.assertAlmostEqual(result.judge_ratio, 1.0)

    def test_report_fields(self):
        result = self.executor.to_eve_format()
        self.assertEqual(result.report["total_instances"], 3)
        self.assertEqual(result.report["resolved_instances"], 2)

    def test_details_count(self):
        result = self.executor.to_eve_format()
        self.assertEqual(len(result.details), 3)
        self.assertEqual(len(result.judge_details), 3)

    def test_detail_oss_url(self):
        result = self.executor.to_eve_format()
        self.assertIn("results.tgz", result.detail_oss_url)

    def test_missing_files_raises(self):
        (self.trace_dir / "batch_summary.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.executor.to_eve_format()


class TestParseTraceDir(unittest.TestCase):
    def test_default(self):
        config = ClawEvalConfig(work_dir=Path("/tmp/work"), extra_args=[])
        executor = ClawEvalExecutor(config)
        self.assertEqual(executor.trace_dir, Path("/tmp/work/claw_traces"))

    def test_explicit(self):
        config = ClawEvalConfig(
            work_dir=Path("/tmp/work"),
            extra_args=["--trace-dir", "/custom/traces", "--other"],
        )
        executor = ClawEvalExecutor(config)
        self.assertEqual(executor.trace_dir, Path("/custom/traces"))


class TestDeepMerge(unittest.TestCase):
    def test_flat(self):
        base = {"a": 1, "b": 2}
        result = _deep_merge(base, {"b": 3, "c": 4})
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_nested(self):
        base = {"model": {"api_key": "k1", "base_url": "u1"}}
        result = _deep_merge(base, {"model": {"extra_body": {"top_p": 0.9}}})
        self.assertEqual(result["model"]["api_key"], "k1")
        self.assertEqual(result["model"]["extra_body"], {"top_p": 0.9})

    def test_override_scalar_with_dict(self):
        base = {"a": 1}
        result = _deep_merge(base, {"a": {"nested": True}})
        self.assertEqual(result, {"a": {"nested": True}})


class TestApplyConfigOverride(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config_path = Path(self.tmp) / "config.yaml"
        base_config = {
            "model": {"api_key": "key1", "model_id": "m1"},
            "judge": {"enabled": True},
        }
        with open(self.config_path, "w") as f:
            yaml.dump(base_config, f)

        self.config = ClawEvalConfig(
            work_dir=Path(self.tmp),
            extra_args=["--config", str(self.config_path), "--model", "m1"],
        )
        self.executor = ClawEvalExecutor(self.config)

    def test_no_env_var_is_noop(self):
        extra = ["--config", str(self.config_path), "--model", "m1"]
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CONFIG_OVERRIDE", None)
            result = self.executor._apply_config_override(extra)
        self.assertEqual(result, extra)

    def test_merges_and_replaces_path(self):
        override = {"model": {"extra_body": {"top_p": 0.9}}, "judge": {"enabled": False}}
        extra = ["--config", str(self.config_path), "--model", "m1"]
        with patch.dict(os.environ, {"CONFIG_OVERRIDE": json.dumps(override)}):
            result = self.executor._apply_config_override(extra)

        merged_path = Path(result[1])
        self.assertTrue(merged_path.exists())
        self.assertNotEqual(str(merged_path), str(self.config_path))

        with open(merged_path) as f:
            merged = yaml.safe_load(f)
        self.assertEqual(merged["model"]["api_key"], "key1")
        self.assertEqual(merged["model"]["extra_body"], {"top_p": 0.9})
        self.assertFalse(merged["judge"]["enabled"])

    def test_no_config_flag_logs_warning(self):
        extra = ["--model", "m1"]
        with patch.dict(os.environ, {"CONFIG_OVERRIDE": '{"a":1}'}):
            result = self.executor._apply_config_override(extra)
        self.assertEqual(result, extra)

    def test_relative_config_path(self):
        rel_config = Path("config.yaml")
        with open(Path(self.tmp) / "config.yaml", "w") as f:
            yaml.dump({"model": {"api_key": "k"}}, f)

        extra = ["--config", str(rel_config)]
        with patch.dict(os.environ, {"CONFIG_OVERRIDE": '{"model":{"extra_body":{"x":1}}}'}):
            result = self.executor._apply_config_override(extra)

        merged_path = Path(result[1])
        with open(merged_path) as f:
            merged = yaml.safe_load(f)
        self.assertEqual(merged["model"]["extra_body"], {"x": 1})
        self.assertEqual(merged["model"]["api_key"], "k")


if __name__ == "__main__":
    unittest.main()
