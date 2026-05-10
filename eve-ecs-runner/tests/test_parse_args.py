import sys
import unittest


class TestParseArgs(unittest.TestCase):
    def _parse(self, argv):
        old_argv = sys.argv
        sys.argv = ["eve_ecs_runner"] + argv
        try:
            from eve_ecs_runner.main import parse_args

            return parse_args()
        finally:
            sys.argv = old_argv

    def test_submit(self):
        args = self._parse(["submit", "--benchmark", "claw-eval", "--run-id", "r1"])
        self.assertEqual(args.command, "submit")
        self.assertEqual(args.benchmark, "claw-eval")
        self.assertEqual(args.run_id, "r1")

    def test_worker(self):
        args = self._parse(["worker", "--benchmark", "claw-eval"])
        self.assertEqual(args.command, "worker")

    def test_extra_args_captured(self):
        args = self._parse([
            "submit", "--benchmark", "claw-eval",
            "--model", "gpt-4", "--parallel", "8",
        ])
        self.assertIn("--model", args.extra_args)
        self.assertIn("gpt-4", args.extra_args)
        self.assertIn("--parallel", args.extra_args)


if __name__ == "__main__":
    unittest.main()
