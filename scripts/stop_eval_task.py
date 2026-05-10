#!/usr/bin/env python3
"""
claw-eval 评测任务停止脚本

用法:
    python3 /mnt/data/workspace/claw-eval-ecs/scripts/stop_eval_task.py [--force]

功能:
  - 读取 worker.pid 文件获取运行中的任务进程
  - 优雅停止任务进程 (SIGTERM)
  - 使用 --force 参数强制终止 (SIGKILL)
  - 清理相关容器和资源
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

WORK_DIR = Path("/mnt/data/workspace/claw-eval-ecs")
WORKER_PID = WORK_DIR / "worker.pid"
WORKER_LOG = WORK_DIR / "worker.log"

SEPARATOR = "=" * 80


def check_process_exists(pid: int) -> bool:
    """检查进程是否存在"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_process_info(pid: int) -> str:
    """获取进程信息"""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid,ppid,cmd"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except Exception as e:
        return f"获取进程信息失败: {e}"


def stop_process(pid: int, force: bool = False) -> bool:
    """停止进程"""
    if not check_process_exists(pid):
        print(f"进程 {pid} 不存在或已停止")
        return True

    sig = signal.SIGKILL if force else signal.SIGTERM
    sig_name = "SIGKILL" if force else "SIGTERM"

    try:
        print(f"发送 {sig_name} 信号到进程 {pid}...")
        os.kill(pid, sig)

        # 等待进程结束
        max_wait = 30 if not force else 5
        for i in range(max_wait):
            time.sleep(1)
            if not check_process_exists(pid):
                print(f"进程 {pid} 已成功停止")
                return True
            if i % 5 == 0 and i > 0:
                print(f"等待进程停止... ({i}/{max_wait}s)")

        if not force:
            print(f"进程 {pid} 在 {max_wait} 秒内未停止，请使用 --force 参数强制终止")
            return False
        else:
            print(f"进程 {pid} 强制终止失败")
            return False

    except PermissionError:
        print(f"权限不足，无法停止进程 {pid}")
        return False
    except Exception as e:
        print(f"停止进程时出错: {e}")
        return False


def cleanup_log_file():
    """清理日志文件"""
    if WORKER_LOG.exists():
        try:
            file_size = WORKER_LOG.stat().st_size
            size_mb = file_size / (1024 * 1024)
            print(f"\n清理日志文件 {WORKER_LOG} (大小: {size_mb:.2f} MB)...")
            WORKER_LOG.unlink()
            print("日志文件已删除")
        except Exception as e:
            print(f"删除日志文件失败: {e}")
    else:
        print(f"\n日志文件不存在: {WORKER_LOG}")


def cleanup_containers():
    """清理相关容器"""
    print("\n清理相关容器...")
    try:
        # 查找并停止 claw-eval 相关容器
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", "name=claw-eval", "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0 and result.stdout.strip():
            container_ids = result.stdout.strip().split("\n")
            print(f"找到 {len(container_ids)} 个相关容器")

            for cid in container_ids:
                print(f"停止容器 {cid}...")
                subprocess.run(["docker", "stop", cid], timeout=30)
                print(f"删除容器 {cid}...")
                subprocess.run(["docker", "rm", cid], timeout=10)

            print("容器清理完成")
        else:
            print("未找到相关容器")

    except subprocess.TimeoutExpired:
        print("容器清理超时")
    except FileNotFoundError:
        print("Docker 未安装或不可用，跳过容器清理")
    except Exception as e:
        print(f"清理容器时出错: {e}")


def main():
    parser = argparse.ArgumentParser(description="停止 claw-eval 评测任务")
    parser.add_argument("--force", action="store_true", help="强制终止进程 (SIGKILL)")
    parser.add_argument("--no-cleanup", action="store_true", help="不清理容器和日志")
    parser.add_argument("--keep-log", action="store_true", help="保留日志文件")
    args = parser.parse_args()

    print(SEPARATOR)
    print("claw-eval 任务停止脚本")
    print(SEPARATOR)

    # 检查 PID 文件
    if not WORKER_PID.exists():
        print(f"\n未找到 PID 文件: {WORKER_PID}")
        print("任务可能未运行或已停止")
        sys.exit(0)

    # 读取 PID
    try:
        with open(WORKER_PID) as f:
            pid = int(f.read().strip())
    except Exception as e:
        print(f"\n读取 PID 文件失败: {e}")
        sys.exit(1)

    print(f"\n读取到任务进程 PID: {pid}")

    # 获取进程信息
    proc_info = get_process_info(pid)
    if proc_info:
        print("\n进程信息:")
        print(proc_info)

    # 停止进程
    print()
    success = stop_process(pid, force=args.force)

    if success:
        # 删除 PID 文件
        try:
            WORKER_PID.unlink()
            print(f"已删除 PID 文件: {WORKER_PID}")
        except Exception as e:
            print(f"删除 PID 文件失败: {e}")

        # 清理容器和日志
        if not args.no_cleanup:
            cleanup_containers()
            if not args.keep_log:
                cleanup_log_file()

        print("\n" + SEPARATOR)
        print("任务已成功停止")
        print(SEPARATOR)
        sys.exit(0)
    else:
        print("\n" + SEPARATOR)
        print("任务停止失败")
        print(SEPARATOR)
        sys.exit(1)


if __name__ == "__main__":
    main()
