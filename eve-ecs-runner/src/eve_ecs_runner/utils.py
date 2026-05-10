import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)


def check_root() -> None:
    if os.geteuid() != 0:
        logger.error("This script must be run as root")
        sys.exit(1)


def cleanup_environment():
    logger.info("Cleaning up environment...")
    try:
        cmd = "pgrep -f '(swebench|claw-eval|infer|eval)'"
        pids = subprocess.getoutput(cmd).split()
        current_pid = str(os.getpid())
        targets = [p for p in pids if p != current_pid]
        if targets:
            subprocess.run(["kill", "-9"] + targets, capture_output=True)
    except Exception as e:
        logger.warning("Failed to clean up processes: %s", e)

    try:
        res = subprocess.getoutput("docker ps -aq")
        if res.strip():
            subprocess.run(["docker", "rm", "-f"] + res.split(), capture_output=True)
    except Exception as e:
        logger.warning("Failed to clean up Docker containers: %s", e)
