import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from eve_ecs_runner.base_config import BaseConfig, _str_val


class TestStrVal(unittest.TestCase):
    def test_cli_arg_wins(self):
        args = SimpleNamespace(foo="from_cli")
        os.environ["TEST_FOO"] = "from_env"
        try:
            self.assertEqual(_str_val(args, "foo", "TEST_FOO"), "from_cli")
        finally:
            del os.environ["TEST_FOO"]

    def test_env_fallback(self):
        args = SimpleNamespace(foo=None)
        os.environ["TEST_FOO"] = "from_env"
        try:
            self.assertEqual(_str_val(args, "foo", "TEST_FOO"), "from_env")
        finally:
            del os.environ["TEST_FOO"]

    def test_none_when_neither(self):
        args = SimpleNamespace(foo=None)
        os.environ.pop("TEST_FOO", None)
        self.assertIsNone(_str_val(args, "foo", "TEST_FOO"))

    def test_none_args(self):
        os.environ["TEST_FOO"] = "from_env"
        try:
            self.assertEqual(_str_val(None, "foo", "TEST_FOO"), "from_env")
        finally:
            del os.environ["TEST_FOO"]


class TestBaseConfig(unittest.TestCase):
    def test_validate_raises_on_unknown(self):
        config = BaseConfig()
        with self.assertRaises(ValueError):
            config.validate()

    def test_validate_passes(self):
        config = BaseConfig(run_id="test-123")
        config.validate()  # should not raise

    def test_oss_bucket(self):
        config = BaseConfig(run_id="run-1", oss_root="oss://bucket/path")
        self.assertEqual(config.oss_bucket, "oss://bucket/path/run-1")

    def test_oss_bucket_strips_trailing_slash(self):
        config = BaseConfig(run_id="run-1", oss_root="oss://bucket/path/")
        self.assertEqual(config.oss_bucket, "oss://bucket/path/run-1")

    def test_eve_file_path(self):
        work_dir = Path("/tmp/test")
        config = BaseConfig(work_dir=work_dir, eve_file="result.json")
        self.assertEqual(config.eve_file_path, Path("/tmp/test/result.json"))


if __name__ == "__main__":
    unittest.main()
