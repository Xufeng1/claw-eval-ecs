import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Parsing helpers: CLI args take priority over env vars.
# Shared by all subclass from_args() implementations.
# ---------------------------------------------------------------------------


def _str_val(args, attr: str, env_key: str) -> str | None:
    """Return the CLI arg value, or env var value, or None if neither is set."""
    val = getattr(args, attr, None) if args is not None else None
    if val is not None:
        return val
    return os.environ.get(env_key)


# ---------------------------------------------------------------------------
# BaseConfig: fields shared by all benchmarks
# ---------------------------------------------------------------------------


@dataclass
class BaseConfig:
    # Unique identifier for this evaluation run, assigned by the EVE platform (required).
    run_id: str = "unknown"
    # Filename for the EVE evaluation result JSON.
    eve_file: str = "eve_eval_result.json"
    # OSS bucket root URL for uploading results;
    # subclasses should override with a benchmark-specific path.
    oss_root: str = ""

    # Working directory at the time the command was invoked.
    # All output files (logs, results, traces) are written here.
    work_dir: Path = field(default_factory=Path.cwd)
    # Path to the worker process log file.
    log_file: Path = field(default_factory=Path)

    # Unrecognised CLI args forwarded verbatim to the downstream benchmark CLI.
    extra_args: list = field(default_factory=list)

    @classmethod
    def _base_kwargs(cls, args=None) -> dict:
        """Parse common fields from args and env vars.

        Called by subclass from_args() implementations and unpacked with **.
        """
        work_dir = Path.cwd()

        # Only include values that are explicitly set; let dataclass defaults apply for the rest.
        return {
            k: v
            for k, v in dict(
                run_id=_str_val(args, "run_id", "RUN_ID"),
                eve_file=os.environ.get("EVE_FILE"),
                work_dir=work_dir,
                log_file=work_dir / "worker.log",
                extra_args=getattr(args, "extra_args", None),
            ).items()
            if v is not None
        }

    @property
    def eve_file_path(self) -> Path:
        return self.work_dir / self.eve_file

    @property
    def oss_bucket(self) -> str:
        return f"{self.oss_root.rstrip('/')}/{self.run_id}"

    def validate(self) -> None:
        if self.run_id == "unknown":
            raise ValueError("RUN_ID not set (use --run-id or RUN_ID env var)")
