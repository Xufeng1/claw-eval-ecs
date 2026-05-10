import argparse
import logging
import os
import sys
from dataclasses import fields
from pathlib import Path

from dotenv import load_dotenv

from .benchmarks import REGISTRY, make_config, make_executor
from .launcher import launch_worker
from .storage import finalize_storage, upload_to_oss
from .utils import check_root, cleanup_environment

logger = logging.getLogger(__name__)


def parse_args():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--benchmark",
        choices=list(REGISTRY.keys()),
        required=True,
        help="Benchmark type to run",
    )
    common.add_argument(
        "--run-id",
        help="Unique run ID for this evaluation (or set RUN_ID env var)",
    )
    common.add_argument("--oss-root", help="OSS root path for uploading results")

    parser = argparse.ArgumentParser(description="EVE Benchmark Runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Two-phase "submit + worker" pattern:
    #
    # The caller (e.g. an ECS instance controlled by the upstream eval
    # platform) invokes "submit" via a remote command and expects a quick
    # response.  "submit" validates the config, spawns "worker" as a
    # detached daemon process (new session, no terminal IO), and returns
    # immediately with the PID and log path.
    #
    # The "worker" process then runs the actual benchmark (which may take
    # hours), writes logs to a file, and uploads results to OSS on exit.
    # Because it is fully detached, it survives after the calling
    # session (SSH connection, etc.) ends.
    subparsers.add_parser(
        "submit",
        parents=[common],
        help="Validate config and spawn worker as a detached daemon",
    )
    subparsers.add_parser(
        "worker",
        parents=[common],
        help="Run the benchmark (called internally by submit)",
    )

    # Benchmark-specific args (e.g. --model, --parallel, --filter) are not
    # declared here.  They are captured as extra_args and forwarded verbatim
    # to the downstream benchmark CLI (e.g. claw-eval batch).
    args, extra = parser.parse_known_args()
    args.extra_args = extra
    return args


def handle_submit(args):
    # TODO: check if we really need to "check root"
    check_root()
    # TODO: each benchmark should have its own cleanup logic
    cleanup_environment()

    config = make_config(args)
    config.validate()

    pid = launch_worker(config)

    print("=" * 50)
    print("Task submitted successfully.")
    print(f"PID: {pid}")
    print(f"Task: {args.benchmark}")
    print(f"Log file: {config.log_file}")
    print("=" * 50)


def _log_config(config):
    logger.info("Config:")
    for f in fields(config):
        logger.info("  %s = %r", f.name, getattr(config, f.name))


def handle_worker(args):
    # Compute the log path before make_config so that any config errors are
    # captured in the log file (the worker process has stdout/stderr → DEVNULL).
    log_file = Path.cwd() / "worker.log"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    log_level_name = os.environ.get("LOG_LEVEL", "INFO")
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)

    logger.info("=" * 60)
    logger.info("Worker started | PID: %d | Task: %s", os.getpid(), args.benchmark)
    logger.info("  argv: %s", sys.argv)
    logger.info("  cwd:  %s", Path.cwd())
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("Environment variables:")
        for k, v in sorted(os.environ.items()):
            logger.debug("  %s = %s", k, v)
    logger.info("=" * 60)

    config = None
    executor = None
    try:
        config = make_config(args)
        _log_config(config)
        executor = make_executor(args.benchmark, config)
        executor.run_all()

    except Exception as e:
        logger.critical("Worker crashed: %s", e, exc_info=True)
    finally:
        # Log before finalize_storage so this line is included in the uploaded log.
        logger.info("Worker process exiting.")
        if executor is not None:
            finalize_storage(config, executor)
        elif config is not None:
            logger.info("Executor not initialized; uploading raw log only.")
            upload_to_oss(log_file, config.oss_root, config.run_id)
        # If config itself failed, there is no OSS target to upload to.


def main():
    load_dotenv()
    args = parse_args()

    if args.command == "submit":
        handle_submit(args)
    elif args.command == "worker":
        handle_worker(args)


if __name__ == "__main__":
    main()
