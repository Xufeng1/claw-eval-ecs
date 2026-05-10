import unittest
from types import SimpleNamespace

from eve_ecs_runner.benchmarks import make_config, make_executor
from eve_ecs_runner.benchmarks.claw_eval.config import ClawEvalConfig
from eve_ecs_runner.benchmarks.claw_eval.executor import ClawEvalExecutor


class TestRegistry(unittest.TestCase):
    def test_make_config_valid(self):
        args = SimpleNamespace(benchmark="claw-eval", run_id="r1", oss_root=None, extra_args=[])
        config = make_config(args)
        self.assertIsInstance(config, ClawEvalConfig)

    def test_make_config_unknown(self):
        args = SimpleNamespace(benchmark="nonexistent")
        with self.assertRaises(ValueError):
            make_config(args)

    def test_make_executor_valid(self):
        config = ClawEvalConfig(run_id="r1")
        executor = make_executor("claw-eval", config)
        self.assertIsInstance(executor, ClawEvalExecutor)

    def test_make_executor_unknown(self):
        config = ClawEvalConfig()
        with self.assertRaises(ValueError):
            make_executor("nonexistent", config)


if __name__ == "__main__":
    unittest.main()
