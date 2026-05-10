import tarfile
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from eve_ecs_runner.storage import archive_results


class TestArchiveResults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.config = SimpleNamespace(work_dir=Path(self.tmp))

    def test_creates_tgz(self):
        # Create a sample artifact file
        artifact = Path(self.tmp) / "trace.json"
        artifact.write_text('{"key": "value"}')

        archive = archive_results(self.config, [artifact])
        self.assertTrue(archive.exists())
        self.assertTrue(archive.name.endswith(".tgz"))

        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            self.assertTrue(any("trace.json" in n for n in names))

    def test_creates_tgz_with_dir(self):
        artifact_dir = Path(self.tmp) / "traces"
        artifact_dir.mkdir()
        (artifact_dir / "a.json").write_text("{}")
        (artifact_dir / "b.json").write_text("{}")

        archive = archive_results(self.config, [artifact_dir])
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            self.assertTrue(any("a.json" in n for n in names))
            self.assertTrue(any("b.json" in n for n in names))

    def test_missing_artifact_skipped(self):
        missing = Path(self.tmp) / "nonexistent.json"
        # Should not raise, just skip
        archive = archive_results(self.config, [missing])
        self.assertTrue(archive.exists())


if __name__ == "__main__":
    unittest.main()
