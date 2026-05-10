from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class JudgeDetail:
    """Structure of a single entry in the `judge_details` list.

    Field requirements follow the EVE platform specification.
    See: <https://yuque.antfin.com/fl47i2/mqwmvz/wiskrkbmmvfapaed>
    """

    # -- Required by EVE ------------------------------------------------

    idx: int
    prompt: str
    origin_prompt: str
    origin_prompt_hash: str

    origin_prediction: str | list
    """Raw model output. `str` for single-turn; `list` for multi-turn
    or pass@k scenarios.
    """
    processed_prediction: str | list
    """Post-processed model output (same type semantics as above)."""
    reference: str | list[str]
    """Reference answer.  `str` for single-turn / pass@k;
    `list[str]` for multi-turn.
    """
    correct: bool | list[bool] | float
    """Whether the sample is correct. `bool` for single-turn;
    `list[bool]` for multi-turn / pass@k; `float` when an exact
    binary judgement is not possible.
    """

    # -- Optional -------------------------------------------------------

    is_multiturn: bool = False
    """Must be `True` for multi-turn datasets."""
    group_score: float | None = None
    """Per-sample score under pass@k (omit for non-pass@k benchmarks)."""
    llm_judgement: str | list[str] | None = None
    """Raw LLM-judge output. Empty string indicates a judge failure.
    `None` or absent → EVE will not track judge success rate.
    """
    processed_llm_judgement: str | list[str] | None = None
    """Post-processed LLM-judge output (same semantics as above)."""
    ext_info: dict = field(default_factory=dict)
    """Arbitrary extra information displayed in the EVE UI."""


@dataclass
class EveResult:
    """Structure of the EVE evaluation result JSON file.

    The EVE platform polls the OSS bucket for this file to determine that
    the evaluation task has finished.  Both successful runs and failures
    must produce a file conforming to this structure.
    """

    score: float = 0.0
    judge_ratio: float = 0.0
    report: dict = field(default_factory=dict)
    details: list[dict] = field(default_factory=list)
    judge_details: list[JudgeDetail] = field(default_factory=list)
    detail_oss_url: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def error(cls, error_msg: str) -> EveResult:
        """Create a minimal result that signals a failed evaluation."""
        return cls(
            report={
                "total_instances": 0,
                "resolved_instances": 0,
                "error": error_msg,
            },
            metadata={
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            },
        )
