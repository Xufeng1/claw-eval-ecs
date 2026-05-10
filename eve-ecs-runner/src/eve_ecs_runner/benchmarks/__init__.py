from __future__ import annotations

from typing import TYPE_CHECKING

from .claw_eval import ClawEvalConfig, ClawEvalExecutor

if TYPE_CHECKING:
    from eve_ecs_runner.base_config import BaseConfig
    from eve_ecs_runner.base_executor import BaseExecutor

# Registry: add imports above and one entry below to register a new benchmark.
REGISTRY: dict[str, dict] = {
    "claw-eval": {
        "config": ClawEvalConfig,
        "executor": ClawEvalExecutor,
    },
}


def make_config(args=None) -> BaseConfig:
    """Instantiate the Config subclass for the given args.benchmark."""
    benchmark = getattr(args, "benchmark", None)
    if benchmark not in REGISTRY:
        raise ValueError(f"Unknown benchmark: {benchmark!r}")
    return REGISTRY[benchmark]["config"].from_args(args)


def make_executor(benchmark: str, config: BaseConfig) -> BaseExecutor:
    """Instantiate the Executor for the given benchmark name."""
    if benchmark not in REGISTRY:
        raise ValueError(f"Unknown benchmark: {benchmark!r}")
    return REGISTRY[benchmark]["executor"](config)
