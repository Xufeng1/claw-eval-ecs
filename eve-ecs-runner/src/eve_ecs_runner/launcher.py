import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_main_script_path() -> str:
    main_file = getattr(sys.modules.get("__main__"), "__file__", None) or sys.argv[0]
    return str(Path(main_file).resolve())


def launch_worker(config):
    python_exe = sys.executable
    main_script = get_main_script_path()

    # Forward all args verbatim by replacing the "submit" subcommand with "worker".
    # Both subcommands share the same parent parser, so no arg list needs to be maintained here.
    cmd = [python_exe, main_script, "worker"] + sys.argv[2:]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            close_fds=True,
        )

        pid_file = Path(config.work_dir) / "worker.pid"
        pid_file.write_text(str(process.pid))

        return process.pid

    except Exception:
        logger.exception("Failed to launch background worker process")
        raise
