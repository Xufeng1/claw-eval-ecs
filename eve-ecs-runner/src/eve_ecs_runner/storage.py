import logging
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

logger = logging.getLogger(__name__)


def archive_results(config, artifacts: list) -> Path:
    archive_path = config.work_dir / "results.tgz"
    temp_dir = config.work_dir / "_temp_results"

    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir()

        for path in artifacts:
            path = Path(path)
            if not path.exists():
                logger.warning("Artifact not found, skipping: %s", path)
                continue

            target = temp_dir / path.name
            if path.is_dir():
                shutil.copytree(path, target)
            else:
                shutil.copy2(path, target)

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(temp_dir, arcname="results")

        logger.info("Archive created: %s", archive_path)
        return archive_path
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


# TODO: migrate to oss sdk
def upload_to_oss(local_path: Path, oss_root: str, run_id: str) -> bool:
    """Upload a single file to the run directory on OSS using ossutil."""
    if not shutil.which("ossutil"):
        logger.error("ossutil not found, skipping upload.")
        return False

    # Target: oss://bucket/path/{run_id}/{filename}
    target_url = f"{oss_root.rstrip('/')}/{run_id}/{local_path.name}"

    cmd = ["ossutil", "cp", "-f", str(local_path), target_url]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logger.info("Uploaded to OSS: %s", target_url)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("OSS upload failed: %s", e.stderr)
        return False


def finalize_storage(config, executor):
    """Upload artifacts, logs, and finally the EVE result file to OSS.

    NOTE: Upload order matters: EVE polls the OSS bucket for the result file
    to determine that the task has finished, then releases the ECS
    instance.  Therefore the result file must be uploaded **last**, after
    all other artifacts and logs are already in place.
    """
    logger.info("Starting finalization...")

    # 1. Archive and upload benchmark artifacts (traces, etc.).
    artifacts = executor.get_artifacts()
    if artifacts:
        archive_path = archive_results(config, artifacts)
        upload_to_oss(archive_path, config.oss_root, config.run_id)
        archive_path.unlink()

    # 2. Flush and upload the log file.
    logger.info("Uploading log file...")
    for handler in logging.getLogger().handlers:
        handler.flush()
    sys.stdout.flush()
    sys.stderr.flush()
    upload_to_oss(config.log_file, config.oss_root, config.run_id)

    # 3. Upload the EVE result file LAST.  Once EVE detects this file,
    #    it considers the task complete and may release the ECS instance
    #    at any time, so nothing should follow this step.
    eve_file = config.eve_file_path
    if eve_file.exists():
        upload_to_oss(eve_file, config.oss_root, config.run_id)
