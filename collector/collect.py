#!/usr/bin/env python3
"""Collect privacy-preserving HiPerGator group allocation snapshots.

Run on HiPerGator after `module load ufrc`. This script never transmits data.
It writes only aggregate allocation usage and counts of pending reasons.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

DEFAULT_ACCOUNT = "qi855292.ucf"
NUM = r"\d+(?:\.\d+)?"
ALLOCATION_ROW = re.compile(
    rf"^\s*(?P<account>[\w.\-]+)\s+(?P<hours>{NUM})\s+"
    rf"(?P<cpu>{NUM})\s+(?P<memory>{NUM})\s+(?P<gpu>{NUM})(?:\s|$)"
)
USAGE_ROW = re.compile(
    rf"^\s*(?P<kind>Investment|Burst)\s+\((?P<qos>[^)]+)\):\s+"
    rf"(?P<cpu_running>{NUM})\s+(?P<mem_running>{NUM})\s+"
    rf"(?P<cpu_pending>{NUM})\s+(?P<mem_pending>{NUM})\s+"
    rf"(?P<cpu_total>{NUM})\s+(?P<mem_total>{NUM})"
)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def number(value: str) -> int | float:
    result = float(value)
    return int(result) if result.is_integer() else round(result, 3)


def parse_slurm_info(text: str, account: str) -> dict:
    """Extract group allocation and job reservations from official slurmInfo text."""
    clean = ANSI_ESCAPE.sub("", text)
    allocation = None
    usage: dict[str, dict] = {}
    for line in clean.splitlines():
        row = ALLOCATION_ROW.match(line)
        if row and row.group("account") == account:
            allocation = {
                "cpu_total": number(row.group("cpu")),
                "memory_total_gb": number(row.group("memory")),
                "gpu_total": number(row.group("gpu")),
            }
        match = USAGE_ROW.match(line)
        if not match:
            continue
        kind = match.group("kind").lower()
        usage[kind] = {
            "qos": match.group("qos"),
            "cpu_running": number(match.group("cpu_running")),
            "memory_running_gb": number(match.group("mem_running")),
            "cpu_pending": number(match.group("cpu_pending")),
            "memory_pending_gb": number(match.group("mem_pending")),
        }

    if allocation is None:
        raise ValueError(
            f"slurmInfo 中找不到账户 {account!r} 的 Allocation summary。"
            "请核对账户名，并检查 UFRC 命令输出是否有变化。"
        )
    if "investment" not in usage:
        raise ValueError(
            "slurmInfo 中找不到 Investment CPU/MEM Usage 行。"
            "请核对 QOS 和实际命令输出；不会把未知占用错误地显示为 0。"
        )
    investment = allocation | usage["investment"]
    burst = usage.get("burst", {
        "qos": account + "-b",
        "cpu_running": 0,
        "memory_running_gb": 0,
        "cpu_pending": 0,
        "memory_pending_gb": 0,
    })
    return {"investment": investment, "burst": burst}


def parse_pending_queue(text: str) -> dict:
    """Input comes from squeue -t PD -h -o '%r|%q'. No usernames/IDs."""
    counts = Counter()
    qos_counts = Counter()
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.strip().split("|", 1)
        if len(fields) != 2:
            raise ValueError("squeue 输出格式不正确，期待 'reason|qos'。")
        reason, qos = fields
        counts[reason.strip() or "Unknown"] += 1
        qos_counts[qos.strip() or "Unknown"] += 1
    return {
        "pending_total": sum(counts.values()),
        "reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(counts.items(), key=lambda p: (-p[1], p[0]))
        ],
        "by_qos": dict(sorted(qos_counts.items())),
    }


def run_command(argv: list[str]) -> str:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=True, timeout=40)
    except FileNotFoundError as exc:
        raise RuntimeError(f"缺少命令 {argv[0]!r}，请先在 HiPerGator 上运行 module load ufrc。") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"命令 {argv[0]!r} 超时，未更新任何快照。") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"命令 {argv[0]!r} 失败: {exc.stderr.strip()[:500]}") from exc
    return result.stdout


def read_json(path: Path, default):
    try:
        with path.open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return default


def atomic_json_write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".snapshot-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
            file.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def make_snapshot(info_text: str, queue_text: str, account: str, at: datetime | None = None) -> dict:
    at = at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "account": account,
        "collected_at": at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        **parse_slurm_info(info_text, account),
        "queue": parse_pending_queue(queue_text),
    }


def update_history(path: Path, snapshot: dict, max_points: int = 672) -> list[dict]:
    previous = read_json(path, [])
    if not isinstance(previous, list):
        raise ValueError(f"历史文件 {path} 格式不正确，需要一个数组。")
    inv = snapshot["investment"]
    cpu_total = inv["cpu_total"]
    memory_total = inv["memory_total_gb"]
    point = {
        "collected_at": snapshot["collected_at"],
        "cpu_utilization_pct": round(100 * inv["cpu_running"] / cpu_total, 2) if cpu_total else 0,
        "memory_utilization_pct": round(100 * inv["memory_running_gb"] / memory_total, 2) if memory_total else 0,
    }
    # A repeated collection timestamp updates the same point.
    previous = [item for item in previous if item.get("collected_at") != point["collected_at"]]
    return (previous + [point])[-max_points:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    parser.add_argument("--slurm-info-file", type=Path, help="测试用：从已保存的 slurmInfo 文本读取")
    parser.add_argument("--queue-file", type=Path, help="测试用：从已保存的 squeue 文本读取")
    args = parser.parse_args(argv)

    try:
        info = (args.slurm_info_file.read_text(encoding="utf-8") if args.slurm_info_file
                else run_command(["slurmInfo", args.account]))
        queue = (args.queue_file.read_text(encoding="utf-8") if args.queue_file
                 else run_command(["squeue", "-A", args.account, "-t", "PD", "-h", "-o", "%r|%q"]))
        snapshot = make_snapshot(info, queue, args.account)
        history_path = args.output_dir / "history.json"
        history = update_history(history_path, snapshot)
        atomic_json_write(args.output_dir / "latest.json", snapshot)
        atomic_json_write(history_path, history)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"采集失败：{exc}", file=sys.stderr)
        return 1

    print(f"已采集 {args.account} · {snapshot['collected_at']}")
    print(f"CPU: {snapshot['investment']['cpu_running']}/{snapshot['investment']['cpu_total']}")
    print(f"RAM: {snapshot['investment']['memory_running_gb']}/{snapshot['investment']['memory_total_gb']} GB")
    print(f"Pending: {snapshot['queue']['pending_total']} jobs")
    print(f"文件: {args.output_dir / 'latest.json'} 和 {history_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
