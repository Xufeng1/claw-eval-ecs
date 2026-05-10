from dataclasses import dataclass

from eve_ecs_runner.base_config import BaseConfig, _str_val

_DEFAULT_OSS_ROOT = "oss://antllm-agentic-jp/ant-eve/claw-eval"


@dataclass
class ClawEvalConfig(BaseConfig):
    # claw-eval-specific OSS bucket, overrides BaseConfig's empty default
    oss_root: str = _DEFAULT_OSS_ROOT

    @classmethod
    def from_args(cls, args=None) -> "ClawEvalConfig":
        base = cls._base_kwargs(args)
        # oss_root needs .rstrip("/") so it is handled separately.
        if (v := _str_val(args, "oss_root", "OSS_ROOT")) is not None:
            base["oss_root"] = v.rstrip("/")
        return cls(**base)
