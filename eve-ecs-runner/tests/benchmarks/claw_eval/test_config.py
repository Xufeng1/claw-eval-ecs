import os
import unittest
from types import SimpleNamespace

from eve_ecs_runner.benchmarks.claw_eval.config import ClawEvalConfig


class TestClawEvalConfig(unittest.TestCase):
    def test_default_oss_root(self):
        config = ClawEvalConfig()
        self.assertEqual(config.oss_root, "oss://antllm-agentic-jp/ant-eve/claw-eval")

    def test_from_args_cli(self):
        args = SimpleNamespace(
            run_id="run-1",
            oss_root="oss://custom/path/",
            extra_args=["--model", "gpt-4"],
        )
        config = ClawEvalConfig.from_args(args)
        self.assertEqual(config.run_id, "run-1")
        self.assertEqual(config.oss_root, "oss://custom/path")  # trailing slash stripped
        self.assertEqual(config.extra_args, ["--model", "gpt-4"])

    def test_from_args_env_fallback(self):
        args = SimpleNamespace(run_id=None, oss_root=None, extra_args=[])
        os.environ["RUN_ID"] = "env-run"
        try:
            config = ClawEvalConfig.from_args(args)
            self.assertEqual(config.run_id, "env-run")
        finally:
            del os.environ["RUN_ID"]


if __name__ == "__main__":
    unittest.main()
