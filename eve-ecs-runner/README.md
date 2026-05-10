# eve-ecs-runner

A lightweight framework for running benchmarks on ECS instances and reporting results to the EVE evaluation platform.

## How It Works

The runner uses a **submit + worker** two-phase pattern:

1. **submit** -- validates config, spawns a detached worker process, and returns immediately (so the upstream caller doesn't time out).
2. **worker** -- runs the actual benchmark (may take hours), writes results in EVE format, and uploads everything to OSS.

```
caller (e.g. ECS eval platform)
  └─ eve_ecs_runner submit ...   # quick, returns PID
       └─ eve_ecs_runner worker  # detached daemon, long-running
            ├─ run benchmark
            ├─ write eve_eval_result.json
            └─ upload artifacts + log + result to OSS
```

## Installation

```bash
pip install .
```

## Usage

```bash
eve_ecs_runner submit \
    --benchmark claw-eval \
    --run-id <RUN_ID> \
    --oss-root <OSS_ROOT> \
    [benchmark-specific flags ...]
```

Unrecognised flags are forwarded verbatim to the downstream benchmark CLI.

## Configuration

| Source | Priority | Example |
|---|---|---|
| CLI args | Highest | `--run-id abc123` |
| Environment variables | Fallback | `RUN_ID=abc123` |
| Dataclass defaults | Lowest | (defined in config classes) |

### Environment Variables

| Variable | Description |
|---|---|
| `RUN_ID` | Unique evaluation run identifier |
| `OSS_ROOT` | OSS bucket root for result uploads |
| `EVE_FILE` | Output filename (default: `eve_eval_result.json`) |
| `LOG_LEVEL` | Logging level for the worker process (default: `INFO`; set to `DEBUG` to dump all environment variables to `worker.log` for troubleshooting) |

## Supported Benchmarks

- **claw-eval** -- Wraps the `claw-eval batch` CLI, converts results to EVE format.

See [`docs/howto/add-benchmark.md`](docs/howto/add-benchmark.md) for how to add a new benchmark.
