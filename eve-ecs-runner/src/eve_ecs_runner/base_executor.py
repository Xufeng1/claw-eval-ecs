import json
import logging
from abc import ABC, abstractmethod

from .base_config import BaseConfig
from .eve_result import EveResult

logger = logging.getLogger(__name__)


class BaseExecutor(ABC):
    def __init__(self, config: BaseConfig):
        self.config = config

    @abstractmethod
    def run_inference(self): ...

    @abstractmethod
    def run_evaluation(self): ...

    @abstractmethod
    def to_eve_format(self) -> EveResult: ...

    def run_all(self):
        try:
            self.run_inference()
            self.run_evaluation()
            results = self.to_eve_format()
            self._write_eve_file(results)
            logger.info("Task completed successfully.")
        except Exception as e:
            logger.exception("Task failed with exception: %s", e)
            self.generate_error_report(str(e))
            raise

    def _write_eve_file(self, result: EveResult):
        output_path = self.config.eve_file_path
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("EVE result file written: %s", output_path)

    def generate_error_report(self, error_msg: str):
        """Write a minimal EVE result file that reports the failure.

        The EVE platform polls the OSS bucket for the result file to
        determine that the evaluation task has finished. If no file is
        produced, EVE will keep waiting indefinitely. Therefore, even
        when the benchmark crashes, we must still emit a result file so
        that EVE can detect the completion and mark the task as failed.
        """
        self._write_eve_file(EveResult.error(error_msg))

    def get_artifacts(self) -> list:
        """Return supplementary files/dirs to archive and upload to OSS.

        This must NOT include the EVE result file (config.eve_file).
        The result file is the signal that tells EVE the task has finished;
        it is always uploaded as the very last step by finalize_storage()
        to ensure all other artifacts are already in place before EVE
        detects the completion and releases the ECS instance.
        """
        return []
