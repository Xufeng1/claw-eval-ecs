#!/usr/bin/env python3
"""
claw-eval 评测任务运行状态检查脚本

用法:
    python3 /mnt/data/workspace/claw-eval-ecs/scripts/check_eval_status.py

读取 /mnt/data/workspace/claw-eval-ecs 下的运行信息并输出:
  - 创建时间 / 模型信息 / Judge模型信息 / 任务启动配置
  - 运行状态 / 运行进度 / 预计剩余完成时间
  - 完成任务数 / 已完成任务评分汇总
  - 异常日志检索 (error/traceback), 样本不超过 10 个
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK_DIR = Path("/mnt/data/workspace/claw-eval-ecs")
TRACE_BASE = WORK_DIR / "claw_traces"
WORKER_LOG = WORK_DIR / "worker.log"
WORKER_PID = WORK_DIR / "worker.pid"
CONFIG_FILE = WORK_DIR / "config.yaml"

SEPARATOR = "=" * 80
SUB_SEP = "-" * 60


def load_yaml_simple(path: Path) -> dict:
    """简易 YAML 解析, 避免依赖 pyyaml (虽然一般有)."""
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        result = {}
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, _, v = line.partition(":")
                    result[k.strip()] = v.strip()
        return result


def find_trace_dir() -> Path | None:
    """查找最新的 trace 输出目录."""
    if not TRACE_BASE.exists():
        return None
    dirs = sorted(TRACE_BASE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    for d in dirs:
        if d.is_dir():
            return d
    return None


def parse_worker_log() -> dict:
    """从 worker.log 提取运行信息: run_id, model, extra_args, judge, 时间等."""
    info = {
        "run_id": None,
        "model": None,
        "base_url": None,
        "api_key_prefix": None,
        "judge_model": None,
        "judge_base_url": None,
        "extra_args": None,
        "start_time": None,
        "tracebacks": [],
    }
    if not WORKER_LOG.exists():
        return info

    with open(WORKER_LOG) as f:
        lines = f.readlines()

    # 提取最后一次启动的信息 (以最后出现的 "Worker started" 为准)
    last_start_idx = None
    for i, line in enumerate(lines):
        if "Worker started" in line or "Config:" in line:
            last_start_idx = i

    # 从最后一段配置块中提取信息
    in_config = False
    for line in lines:
        line = line.strip()
        if "Worker started" in line:
            m = re.search(r"PID:\s*(\d+)", line)
            if m:
                info["pid"] = int(m.group(1))
        if "Config:" in line:
            in_config = True
            continue
        if in_config:
            if "run_id" in line:
                m = re.search(r"run_id\s*=\s*'(.+?)'", line)
                if m:
                    info["run_id"] = m.group(1)
            elif "extra_args" in line:
                info["extra_args"] = line
                in_config = False

    # 提取时间戳 (最后一段的启动时间)
    for line in lines:
        m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        if m:
            info["start_time"] = m.group(1)

    # 最后一次 "Running claw-eval batch" 的时间
    for line in reversed(lines):
        if "Running claw-eval batch" in line:
            m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if m:
                info["start_time"] = m.group(1)
            # 提取参数
            m2 = re.search(r"claw-eval batch (.+)", line)
            if m2:
                args_str = m2.group(1)
                for token_pair in [("--model", "model"), ("--base-url", "base_url"),
                                   ("--parallel", "parallel"), ("--trials", "trials"),
                                   ("--api-key", "api_key_prefix"),
                                   ("--tag", "tag"), ("--filter", "filter"),
                                   ("--range", "range")]:
                    flag, key = token_pair
                    m3 = re.search(rf"{flag}\s+(\S+)", args_str)
                    if m3:
                        val = m3.group(1)
                        if key == "api_key_prefix":
                            val = val[:12] + "..." if len(val) > 12 else val
                        info[key] = val
                if "--sandbox" in args_str:
                    info["sandbox"] = True
                if "--config" in args_str:
                    m3 = re.search(r"--config\s+(\S+)", args_str)
                    if m3:
                        info["config_file"] = m3.group(1)
            break

    # 提取 judge 信息从环境变量
    for line in lines:
        if "JUDGE_MODEL" in line and "=" in line:
            m = re.search(r"JUDGE_MODEL\s*=\s*(\S+)", line)
            if m:
                info["judge_model"] = m.group(1)
        if "JUDGE_BASE_URL" in line and "=" in line:
            m = re.search(r"JUDGE_BASE_URL\s*=\s*(\S+)", line)
            if m:
                info["judge_base_url"] = m.group(1)

    # 提取 traceback 日志 (最多 10 个)
    tb_blocks = []
    current_tb = []
    in_tb = False
    for line in lines:
        stripped = line.strip()
        if "Traceback" in stripped:
            in_tb = True
            current_tb = [stripped]
        elif in_tb:
            current_tb.append(stripped)
            if re.match(r"^\w+Error:", stripped) or re.match(r"^\w+Exception:", stripped):
                tb_blocks.append("\n".join(current_tb))
                current_tb = []
                in_tb = False
    # 去重后最多 10 个
    seen_tb = set()
    unique_tbs = []
    for tb in tb_blocks:
        last_line = tb.strip().split("\n")[-1].strip()
        if last_line not in seen_tb:
            seen_tb.add(last_line)
            unique_tbs.append(tb)
    info["tracebacks"] = unique_tbs[-10:]

    return info


def check_process_alive(pid: int) -> bool:
    """检查进程是否存活."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def get_running_containers() -> list[dict]:
    """获取正在运行的 docker 容器."""
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.CreatedAt}}"],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line or "claw-agent" not in line:
                continue
            parts = line.split("\t")
            containers.append({
                "name": parts[0] if len(parts) > 0 else "?",
                "status": parts[1] if len(parts) > 1 else "?",
                "created": parts[2] if len(parts) > 2 else "?",
            })
        return containers
    except Exception:
        return []


def analyze_traces(trace_dir: Path, log_info: dict | None = None) -> dict:
    """分析 trace 目录下的所有 .jsonl 文件."""
    result = {
        "batch_results": [],
        "trace_files": {},  # task_id -> [files]
        "all_tasks": [],    # 从 tasks/ 目录获取
        "trace_errors": [], # trace 文件中的异常
    }

    # 读取 batch_results.json
    br_path = trace_dir / "batch_results.json"
    if br_path.exists():
        with open(br_path) as f:
            result["batch_results"] = json.load(f)

    # 扫描 trace 文件
    for fp in sorted(trace_dir.glob("*.jsonl")):
        fname = fp.stem
        # 从文件名解析 task_id (去掉末尾的 _hex8)
        m = re.match(r"(.+)_([a-f0-9]{8})$", fname)
        if not m:
            continue
        task_id = m.group(1)
        trace_hash = m.group(2)
        if task_id not in result["trace_files"]:
            result["trace_files"][task_id] = []
        result["trace_files"][task_id].append({
            "file": fp,
            "hash": trace_hash,
            "size": fp.stat().st_size,
            "mtime": fp.stat().st_mtime,
        })

    # 读取 tasks 目录, 按启动时的 --tag / --filter / --range 过滤
    tasks_dir = WORK_DIR / "tasks"
    if tasks_dir.exists():
        all_dirs = sorted([d.name for d in tasks_dir.iterdir() if d.is_dir()])
        tag = (log_info or {}).get("tag")
        filt = (log_info or {}).get("filter")
        rng = (log_info or {}).get("range")
        if tag or filt or rng:
            filtered = []
            for tname in all_dirs:
                if filt and filt not in tname:
                    continue
                if rng:
                    m_rng = re.match(r"(\d+)-(\d+)", rng)
                    if m_rng:
                        lo, hi = int(m_rng.group(1)), int(m_rng.group(2))
                        m_id = re.search(r"(\d+)", tname)
                        if m_id and not (lo <= int(m_id.group(1)) <= hi):
                            continue
                if tag:
                    task_yaml = tasks_dir / tname / "task.yaml"
                    if task_yaml.exists():
                        task_meta = load_yaml_simple(task_yaml)
                        task_tags = task_meta.get("tags", [])
                        if isinstance(task_tags, list) and tag not in task_tags:
                            continue
                    else:
                        continue
                filtered.append(tname)
            result["all_tasks"] = filtered
        else:
            result["all_tasks"] = all_dirs

    # 在 trace 文件中检索 error/traceback (最多 10 个样本)
    # 搜索整行 JSON 文本 (traceback 常被转义嵌入 stderr/content 字段中)
    error_samples = []
    seen_snippets = set()
    for fp in sorted(trace_dir.glob("*.jsonl")):
        if len(error_samples) >= 10:
            break
        try:
            with open(fp) as f:
                for line_no, line in enumerate(f, 1):
                    if len(error_samples) >= 10:
                        break
                    lower = line.lower()
                    if "traceback" not in lower:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 从完整 JSON 字符串中提取 traceback 上下文
                    raw = json.dumps(d, ensure_ascii=False)
                    idx = raw.lower().find("traceback")
                    if idx < 0:
                        continue
                    snippet_raw = raw[max(0, idx):idx + 400]
                    # 反转义以提高可读性
                    snippet = snippet_raw.replace("\\n", "\n").replace("\\\"", '"').replace("\\\\", "\\")
                    # 截取到合理结尾
                    lines_list = snippet.split("\n")
                    trimmed = []
                    for sl in lines_list:
                        trimmed.append(sl.strip())
                        if re.search(r"Error[:.]", sl):
                            break
                    snippet = "\n".join(trimmed[:15])
                    if len(snippet) > 400:
                        snippet = snippet[:400] + "..."
                    # 去重: 同任务+同错误信息只取一个
                    error_sig = re.sub(r"[^a-zA-Z0-9]", "", snippet[:120])
                    m2_task = re.match(r"(.+)_[a-f0-9]{8}$", fp.stem)
                    task_key = m2_task.group(1) if m2_task else fp.stem
                    dedup_key = f"{task_key}:{error_sig}"
                    if dedup_key in seen_snippets:
                        continue
                    seen_snippets.add(dedup_key)

                    task_id = d.get("task_id", "")
                    if not task_id:
                        m2 = re.match(r"(.+)_[a-f0-9]{8}$", fp.stem)
                        task_id = m2.group(1) if m2 else fp.stem
                    error_samples.append({
                        "file": fp.name,
                        "task_id": task_id,
                        "line": line_no,
                        "type": d.get("type", "?"),
                        "snippet": snippet,
                    })
        except Exception:
            pass

    result["trace_errors"] = error_samples
    return result


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h{m:02d}m"


def main():
    print(SEPARATOR)
    print("  CLAW-EVAL 评测任务运行状态报告")
    print(f"  生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEPARATOR)

    # ── 1. 基础信息 ──
    print("\n[1] 基础信息")
    print(SUB_SEP)

    log_info = parse_worker_log()

    print(f"  Run ID       : {log_info.get('run_id', 'N/A')}")
    print(f"  启动时间     : {log_info.get('start_time', 'N/A')}")
    print(f"  模型         : {log_info.get('model', 'N/A')}")
    print(f"  Base URL     : {log_info.get('base_url', 'N/A')}")
    print(f"  API Key      : {log_info.get('api_key_prefix', 'N/A')}")
    print(f"  Judge 模型   : {log_info.get('judge_model', 'N/A')}")
    print(f"  Judge URL    : {log_info.get('judge_base_url', 'N/A')}")

    # 启动配置
    print(f"\n  --- 任务启动配置 ---")
    print(f"  Trials       : {log_info.get('trials', 'N/A')}")
    print(f"  并行度       : {log_info.get('parallel', 'N/A (默认)')}")
    print(f"  Sandbox      : {'是' if log_info.get('sandbox') else '否/未知'}")
    print(f"  Config       : {log_info.get('config_file', 'N/A')}")

    # config.yaml 补充
    if CONFIG_FILE.exists():
        cfg = load_yaml_simple(CONFIG_FILE)
        if isinstance(cfg, dict):
            model_cfg = cfg.get("model", {})
            if isinstance(model_cfg, dict):
                print(f"  Config模型ID : {model_cfg.get('model_id', 'N/A')}")
                print(f"  Context窗口  : {model_cfg.get('context_window', 'N/A')}")

    # ── 2. 运行状态 ──
    print(f"\n[2] 运行状态")
    print(SUB_SEP)

    # Worker 进程
    pid = log_info.get("pid", None)
    if not pid and WORKER_PID.exists():
        try:
            pid = int(WORKER_PID.read_text().strip())
        except ValueError:
            pass

    if pid:
        alive = check_process_alive(pid)
        print(f"  Worker PID   : {pid} ({'运行中' if alive else '已退出'})")
    else:
        print(f"  Worker PID   : 未知")

    # claw-eval 子进程
    try:
        ps_out = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5,
        ).stdout
        claw_procs = [l for l in ps_out.split("\n") if "claw-eval" in l and "grep" not in l]
        print(f"  claw-eval进程: {len(claw_procs)} 个")
    except Exception:
        print(f"  claw-eval进程: 检测失败")

    # Docker 容器
    containers = get_running_containers()
    print(f"  活跃容器     : {len(containers)} 个")
    for c in containers:
        print(f"    - {c['name']}  ({c['status']})")

    # ── 3. 运行进度 ──
    print(f"\n[3] 运行进度")
    print(SUB_SEP)

    trace_dir = find_trace_dir()
    if not trace_dir:
        print("  未找到 trace 目录")
        return

    print(f"  Trace 目录   : {trace_dir.name}")

    analysis = analyze_traces(trace_dir, log_info)
    all_tasks = analysis["all_tasks"]
    trace_files = analysis["trace_files"]
    batch_results = analysis["batch_results"]
    trials_needed = int(log_info.get("trials", 3))

    completed_ids = {t["task_id"] for t in batch_results}
    tasks_with_traces = set(trace_files.keys())
    tasks_all_trials_done = {
        tid for tid, files in trace_files.items()
        if len(files) >= trials_needed
    }

    running_tasks = tasks_with_traces - tasks_all_trials_done
    grading_tasks = tasks_all_trials_done - completed_ids
    pending_tasks = [t for t in all_tasks if t not in tasks_with_traces]

    total_tasks = len(all_tasks) if all_tasks else "?"

    print(f"  总任务数     : {total_tasks}")
    print(f"  每任务trials : {trials_needed}")
    print(f"  已完成评测   : {len(completed_ids)} 个任务")
    print(f"  评分中       : {len(grading_tasks)} 个任务 (trials完毕, 等待/正在评分)")
    print(f"  运行中       : {len(running_tasks)} 个任务 (trials未跑完)")
    print(f"  等待中       : {len(pending_tasks)} 个任务 (尚未开始)")

    if grading_tasks:
        print(f"  评分中任务   : {', '.join(sorted(grading_tasks))}")
    if running_tasks:
        for tid in sorted(running_tasks):
            files = trace_files[tid]
            print(f"  运行中: {tid} ({len(files)}/{trials_needed} trials)")

    # ── 4. 预计剩余时间 ──
    print(f"\n[4] 预计剩余完成时间")
    print(SUB_SEP)

    if batch_results:
        total_wall_completed = sum(
            sum(tr.get("wall_time_s", 0) for tr in t["trials"])
            for t in batch_results
        )
        total_trials_completed = sum(len(t["trials"]) for t in batch_results)
        avg_wall_per_trial = total_wall_completed / total_trials_completed if total_trials_completed else 0

        remaining_trials = 0
        for tid in running_tasks:
            done = len(trace_files.get(tid, []))
            remaining_trials += trials_needed - done
        for t in pending_tasks:
            remaining_trials += trials_needed

        # 考虑并行度
        parallel = int(log_info.get("parallel", 1)) if log_info.get("parallel") else 1
        # 容器并行
        effective_parallel = max(parallel, len(containers), 1)

        est_remaining_s = (remaining_trials * avg_wall_per_trial) / effective_parallel
        print(f"  已完成trial数  : {total_trials_completed}")
        print(f"  每trial平均耗时: {format_duration(avg_wall_per_trial)}")
        print(f"  剩余trial数    : {remaining_trials}")
        print(f"  预估并行度     : {effective_parallel}")
        print(f"  预计剩余时间   : {format_duration(est_remaining_s)}")
        if est_remaining_s > 0:
            eta = datetime.now() + timedelta(seconds=est_remaining_s)
            print(f"  预计完成时刻   : {eta.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("  (无已完成数据, 无法估算)")

    # ── 5. 已完成任务评分汇总 ──
    print(f"\n[5] 已完成任务评分汇总 ({len(batch_results)} 个)")
    print(SUB_SEP)

    if batch_results:
        header = f"  {'任务ID':<42s} {'名称':<16s} {'avg_score':>10s} {'pass@1':>8s} {'pass^k':>8s} {'通过':>4s}"
        print(header)
        print("  " + "-" * len(header.strip()))

        sorted_results = sorted(batch_results, key=lambda x: x["task_id"])
        pass_count = 0
        fail_count = 0
        total_score = 0

        for t in sorted_results:
            passed = t.get("avg_passed", False)
            if passed:
                pass_count += 1
            else:
                fail_count += 1
            total_score += t.get("avg_score", 0)

            mark = "Yes" if passed else "** No"
            print(
                f"  {t['task_id']:<42s} {t.get('task_name',''):<16s} "
                f"{t['avg_score']:>10.3f} {t.get('pass_at_1',0):>8.2f} "
                f"{t.get('pass_hat_k',0):>8.3f} {mark:>5s}"
            )

        print()
        avg = total_score / len(batch_results) if batch_results else 0
        print(f"  总体: {pass_count} 通过, {fail_count} 失败, "
              f"通过率 {pass_count}/{len(batch_results)} "
              f"({pass_count / len(batch_results) * 100:.1f}%), "
              f"平均分 {avg:.3f}")

        # 资源消耗
        total_tokens = sum(sum(tr.get("tokens", 0) for tr in t["trials"]) for t in batch_results)
        total_input = sum(sum(tr.get("model_input_tokens", 0) for tr in t["trials"]) for t in batch_results)
        total_output = sum(sum(tr.get("model_output_tokens", 0) for tr in t["trials"]) for t in batch_results)
        total_wall = sum(sum(tr.get("wall_time_s", 0) for tr in t["trials"]) for t in batch_results)
        total_model = sum(sum(tr.get("model_time_s", 0) for tr in t["trials"]) for t in batch_results)

        print(f"\n  --- 资源消耗 (已完成部分) ---")
        print(f"  总 tokens   : {total_tokens:>12,}")
        print(f"    input     : {total_input:>12,}")
        print(f"    output    : {total_output:>12,}")
        print(f"  总 wall time: {format_duration(total_wall)}")
        print(f"  总 model time: {format_duration(total_model)}")
    else:
        print("  (暂无已完成任务)")

    # ── 6. 异常日志检索 ──
    print(f"\n[6] 异常日志检索 (error / traceback)")
    print(SUB_SEP)

    # 6a. worker.log 中的 traceback
    worker_tbs = log_info.get("tracebacks", [])
    if worker_tbs:
        print(f"\n  [worker.log] 发现 {len(worker_tbs)} 个 traceback:")
        for i, tb in enumerate(worker_tbs[:10], 1):
            print(f"\n  --- worker.log traceback #{i} ---")
            for line in tb.split("\n"):
                print(f"    {line}")
    else:
        print(f"\n  [worker.log] 无 traceback")

    # 6b. trace 文件中的 error/traceback
    trace_errors = analysis["trace_errors"]
    if trace_errors:
        print(f"\n  [trace files] 发现 {len(trace_errors)} 个异常样本 (最多10个):")
        for i, err in enumerate(trace_errors, 1):
            print(f"\n  --- trace error #{i} ---")
            print(f"    任务: {err['task_id']}")
            print(f"    文件: {err['file']}")
            print(f"    行号: {err['line']}, 类型: {err['type']}")
            print(f"    内容: {err['snippet']}")
    else:
        print(f"\n  [trace files] 未发现 error/traceback 样本")

    print(f"\n{SEPARATOR}")
    print("  报告结束")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
