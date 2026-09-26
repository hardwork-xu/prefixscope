#!/usr/bin/env python3
"""Measure serial page-LRU analysis / 测量串行 page-LRU 分析性能。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any
import uuid

from prefixscope import Profile, Request, replay
from prefixscope.trace import load_jsonl

ROOT = Path(__file__).resolve().parent
METHODS = ("compact", "unbounded", "lru")


def source_version() -> dict[str, Any]:
    """Hash tested implementation independently of result files / 独立哈希被测实现。"""
    paths = sorted((ROOT / "src").rglob("*.py")) + [
        ROOT / "benchmark.py",
        ROOT / "experiments/contract.json",
    ]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=False
    )
    return {
        "git_revision": revision.stdout.strip() if revision.returncode == 0 else None,
        "working_tree_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "source_sha256": digest.hexdigest(),
        "hash_scope": "src/**/*.py + benchmark.py + experiments/contract.json; path NUL bytes NUL",
        "version": "0.1.0",
    }


def sanitized(value: str) -> str:
    """Keep public evidence free of local paths / 公开证据不保留本机路径。"""
    return value.replace(str(ROOT), ".").replace(str(Path.home()), "<home>")


def environment() -> dict[str, Any]:
    """Record relevant runtime, without host/user names / 不记录主机名或用户名。"""
    cpu = platform.processor()
    if platform.system() == "Darwin":
        probe = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode == 0:
            cpu = probe.stdout.strip()
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "cpu": cpu,
        "logical_cpus": os.cpu_count(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "parallelism": 1,
        "timer": "perf_counter_ns",
    }


def load_contract(path: Path) -> dict[str, Any]:
    """Validate the frozen measurement settings / 验证冻结的测量设置。"""
    contract: dict[str, Any] = json.loads(path.read_text())
    if contract.get("schema_version") != 1:
        raise ValueError("Unsupported contract schema / 不支持的约定版本")
    measurement = contract["measurement"]
    if measurement["repeats"] < 3 or measurement["warmup_runs"] < 1:
        raise ValueError("Require >=3 repeats and >=1 warmup / 至少三次重复、一次预热")
    grid = contract["capacity_pages"]
    if grid["start"] < 1 or grid["step"] < 1 or grid["count"] < 1:
        raise ValueError("Capacity grid must be positive / 容量网格须为正数")
    if any(count < 1 or count > grid["count"] for count in contract["capacity_grids"]):
        raise ValueError("Invalid capacity count / 容量数量无效")
    return contract


def capacities_for(contract: dict[str, Any], count: int) -> list[int]:
    grid = contract["capacity_pages"]
    return [grid["start"] + index * grid["step"] for index in range(count)]


def workload_specs(quick: bool) -> list[dict[str, Any]]:
    if quick:
        return [
            {"name": "quick_hot_32", "kind": "hot", "requests": 32, "pages": 4, "groups": 4},
            {"name": "quick_cold_16", "kind": "cold", "requests": 16, "pages": 4},
        ]
    return [
        {
            "name": f"qwen_trace{trace}_{size}",
            "kind": "qwen",
            "path": f"data/raw/qwen_trace{trace}_blksz_16.jsonl",
            "requests": size,
            "namespace": f"qwen-{trace}",
        }
        for trace in ("A", "B")
        for size in (256, 2048)
    ] + [
        {"name": "hot_loop_20000", "kind": "hot", "requests": 20000, "pages": 16, "groups": 8},
        {"name": "cold_scan_4096", "kind": "cold", "requests": 4096, "pages": 16},
        {"name": "mixed_chat_2048", "kind": "mixed", "requests": 2048, "pages": 32},
        {"name": "short_requests_4096", "kind": "short", "requests": 4096, "pages": 1},
    ]


def load_workload(spec: dict[str, Any], seed: int) -> tuple[list[Request], dict[str, Any]]:
    """Build fixed real/synthetic workloads / 生成固定的真实或合成工作负载。"""
    start = time.perf_counter_ns()
    if spec["kind"] == "qwen":
        path = ROOT / spec["path"]
        requests = list(
            load_jsonl(path, format="qwen", limit=spec["requests"], namespace=spec["namespace"])
        )
        if len(requests) != spec["requests"]:
            raise ValueError("Trace is shorter than frozen selection / Trace 少于预设选取数量")
        with path.open("rb") as stream:
            source_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        metadata = {
            "data_kind": "real anonymized public production trace subset",
            "file_sha256": source_digest,
            "selection": f"first {spec['requests']} records, original order",
            "loading_scope": "stream selected records + full-source SHA256 scan with bounded buffer",
        }
    else:
        rng = random.Random(seed)
        requests = []
        for index in range(spec["requests"]):
            kind = spec["kind"]
            if kind == "hot":
                group = index % spec["groups"]
                blocks = tuple(f"hot:{group}:{page}" for page in range(spec["pages"]))
            elif kind == "cold":
                blocks = tuple(f"cold:{index}:{page}" for page in range(spec["pages"]))
            elif kind == "mixed":
                group = rng.randrange(32)
                common = tuple(f"chat:{group}:{page}" for page in range(24))
                tail = tuple(f"chat:{group}:request:{index}:{page}" for page in range(8))
                blocks = common + tail
            elif kind == "short":
                blocks = (f"short:{rng.randrange(1024)}",) if index % 8 else ()
            else:
                raise ValueError(f"Unknown workload / 未知工作负载: {kind}")
            requests.append(Request(blocks=blocks, input_tokens=len(blocks) * 16 + index % 16))
        metadata = {"data_kind": "synthetic", "seed": seed}
    normalized_digest = hashlib.sha256()
    for request in requests:
        normalized_digest.update(
            json.dumps(
                {
                    "blocks": request.blocks,
                    "input_tokens": request.input_tokens,
                    "block_size": request.block_size,
                },
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        )
        normalized_digest.update(b"\n")
    metadata.update(
        normalized_requests_sha256=normalized_digest.hexdigest(),
        normalized_hash_encoding="UTF-8 compact JSON object per request + LF; original order",
        loading_and_normalization_ns=time.perf_counter_ns() - start,
        requests=len(requests),
        full_block_accesses=sum(len(request.blocks) for request in requests),
        input_tokens=sum(request.input_tokens for request in requests),
    )
    return requests, metadata


def execute(
    method: str, requests: list[Request], capacities: list[int]
) -> tuple[list[dict[str, int | float]], dict[str, int]]:
    """Run a fresh analyzer; caller controls timing / 每次运行创建独立分析器。"""
    if method == "lru":
        return replay(requests, capacities), {}
    if method not in ("compact", "unbounded"):
        raise ValueError("Unknown implementation / 未知实现")
    profile = Profile(compact=method == "compact")
    for request in requests:
        profile.observe(request)
    return profile.curve(capacities), profile.stats()


def exact_curve(rows: list[dict[str, int | float]]) -> list[tuple[int, int, int]]:
    return [
        (int(row["capacity_pages"]), int(row["reused_tokens"]), int(row["total_tokens"]))
        for row in rows
    ]


def peak_memory(
    spec: dict[str, Any], method: str, capacities: list[int], seed: int
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "benchmark.py"),
        "--worker",
        json.dumps({"spec": spec, "method": method, "capacities": capacities, "seed": seed}),
    ]
    try:
        process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=300)
        if process.returncode != 0:
            return {"status": "failed", "error": sanitized(process.stderr[-2000:])}
        result: dict[str, Any] = json.loads(process.stdout)
        return result
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return {"status": "failed", "error": sanitized(str(error))}


def worker(payload: dict[str, Any]) -> dict[str, Any]:
    requests, _ = load_workload(payload["spec"], payload["seed"])
    _, stats = execute(payload["method"], requests, payload["capacities"])
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = int(raw if platform.system() == "Darwin" else raw * 1024)
    return {
        "status": "passed",
        "peak_rss_bytes": rss,
        "scope": "fresh subprocess, Python runtime + input loading + analyzer + curve",
        "measurement": "resource.getrusage(RUSAGE_SELF).ru_maxrss",
        "samples": 1,
        "stats": stats,
    }


def run_benchmark(contract: dict[str, Any], quick: bool, seed: int) -> dict[str, Any]:
    """Keep every repetition and failure / 保留每次重复与失败记录。"""
    started = time.perf_counter_ns()
    counts = [1, 8] if quick else contract["capacity_grids"]
    result: dict[str, Any] = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": sanitized("python " + " ".join(sys.argv)),
        "implementation": source_version(),
        "environment": environment(),
        "contract": contract,
        "quick": quick,
        "seed": seed,
        "workloads": [],
        "status": "passed",
        "timed_scope": contract["measurement"]["timed_scope"],
        "normalization_scope": "file read/parse/hash or deterministic synthetic generation; separate",
    }
    rng = random.Random(seed)
    for spec in workload_specs(quick):
        record: dict[str, Any] = {"spec": spec, "status": "passed", "grids": []}
        result["workloads"].append(record)
        try:
            requests, metadata = load_workload(spec, seed)
            record["input"] = metadata
        except (OSError, ValueError, KeyError) as error:
            record.update(status="failed", error=sanitized(f"{type(error).__name__}: {error}"))
            result["status"] = "failed"
            continue
        for count in counts:
            capacities = capacities_for(contract, count)
            expected = replay(requests, capacities)
            grid: dict[str, Any] = {
                "capacity_count": count,
                "capacity_pages": capacities,
                "reference_curve": expected,
                "samples": [],
                "warmups": [],
                "methods": {},
                "order": [],
            }
            record["grids"].append(grid)
            repeats = contract["measurement"]["repeats"]
            for iteration in range(-contract["measurement"]["warmup_runs"], repeats):
                order = list(METHODS)
                rng.shuffle(order)
                grid["order"].append({"iteration": iteration, "methods": order})
                for method in order:
                    sample: dict[str, Any] = {"method": method, "iteration": iteration}
                    try:
                        start = time.perf_counter_ns()
                        rows, stats = execute(method, requests, capacities)
                        elapsed = time.perf_counter_ns() - start
                        correct = exact_curve(rows) == exact_curve(expected)
                        sample.update(duration_ns=elapsed, stats=stats, correct=correct)
                        sample["status"] = "passed" if correct else "failed"
                        if not correct:
                            sample["error"] = (
                                "Curve differs from finite LRU / 容量曲线与有限 LRU 不一致"
                            )
                    except (ValueError, RuntimeError, MemoryError) as error:
                        sample.update(
                            status="failed",
                            duration_ns=None,
                            correct=False,
                            error=sanitized(f"{type(error).__name__}: {error}"),
                        )
                    (grid["warmups"] if iteration < 0 else grid["samples"]).append(sample)
                    if sample["status"] != "passed":
                        record["status"] = result["status"] = "failed"
            for method in METHODS:
                samples = [s for s in grid["samples"] if s["method"] == method]
                durations = [s["duration_ns"] for s in samples if s["duration_ns"] is not None]
                grid["methods"][method] = {
                    "status": "passed"
                    if all(s["status"] == "passed" for s in samples)
                    else "failed",
                    "samples": len(samples),
                    "median_ns": statistics.median(durations) if durations else None,
                    "min_ns": min(durations) if durations else None,
                    "max_ns": max(durations) if durations else None,
                    "requests_per_second": len(requests) * 1e9 / statistics.median(durations)
                    if durations
                    else None,
                }
            if count == max(counts):
                grid["memory"] = {
                    method: peak_memory(spec, method, capacities, seed) for method in METHODS
                }
                if any(item["status"] != "passed" for item in grid["memory"].values()):
                    record["status"] = result["status"] = "failed"
        print(f"{spec['name']}: {record['status']}", file=sys.stderr, flush=True)
    result["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["benchmark_wall_ns"] = time.perf_counter_ns() - started
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "experiments/contract.json",
        help="Frozen experiment contract / 冻结实验约定",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results/benchmark.json",
        help="Raw JSON evidence / 原始 JSON 证据",
    )
    parser.add_argument(
        "--quick", action="store_true", help="Small offline CI run / 小型离线 CI 运行"
    )
    parser.add_argument(
        "--seed", type=int, default=20260927, help="Order/workload seed / 顺序与负载种子"
    )
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return 0
    try:
        contract = load_contract(args.config)
        result = run_benchmark(contract, args.quick, args.seed)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, sanitized(f"Benchmark error / 基准错误: {error}\n"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(sanitized(str(args.output)))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
