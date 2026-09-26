#!/usr/bin/env python3
"""Generate tables and a plot from raw evidence / 从原始证据生成表格与图表。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def summarize(raw: dict[str, Any]) -> dict[str, Any]:
    """Preserve unfavorable and failed results / 保留不利结果和失败状态。"""
    if raw.get("schema_version") != 1 or not isinstance(raw.get("workloads"), list):
        raise ValueError("Unsupported result schema / 不支持的结果格式")
    rows = []
    memory = []
    failures = []
    for workload in raw["workloads"]:
        name = workload["spec"]["name"]
        if workload["status"] != "passed":
            failures.append({"workload": name, "error": workload.get("error", "See raw samples")})
        for grid in workload["grids"]:
            methods = grid["methods"]
            valid = all(methods[method]["status"] == "passed" for method in methods)
            compact = methods["compact"]["median_ns"]
            lru = methods["lru"]["median_ns"]
            unbounded = methods["unbounded"]["median_ns"]
            rows.append(
                {
                    "workload": name,
                    "capacity_count": grid["capacity_count"],
                    "status": "passed" if valid else "failed",
                    "compact_median_ms": compact / 1e6 if compact is not None else None,
                    "lru_median_ms": lru / 1e6 if lru is not None else None,
                    "unbounded_median_ms": unbounded / 1e6 if unbounded is not None else None,
                    "speedup_lru_over_compact": lru / compact
                    if valid and compact and lru
                    else None,
                    "speedup_unbounded_over_compact": unbounded / compact
                    if valid and compact and unbounded
                    else None,
                    "compact_min_ms": methods["compact"]["min_ns"] / 1e6
                    if methods["compact"]["min_ns"] is not None
                    else None,
                    "compact_max_ms": methods["compact"]["max_ns"] / 1e6
                    if methods["compact"]["max_ns"] is not None
                    else None,
                    "samples_per_method": methods["compact"]["samples"],
                    "compact_requests_per_second": methods["compact"]["requests_per_second"],
                }
            )
            if "memory" in grid:
                stats = {}
                for method in ("compact", "unbounded"):
                    candidates = [
                        sample["stats"]
                        for sample in grid["samples"]
                        if sample["method"] == method and sample["status"] == "passed"
                    ]
                    stats[method] = candidates[-1] if candidates else {}
                compact_slots = stats["compact"].get("allocated_slots")
                unbounded_slots = stats["unbounded"].get("allocated_slots")
                memory.append(
                    {
                        "workload": name,
                        "capacity_count": grid["capacity_count"],
                        "compact_allocated_slots": compact_slots,
                        "unbounded_allocated_slots": unbounded_slots,
                        "slots_ratio": compact_slots / unbounded_slots
                        if compact_slots is not None and unbounded_slots
                        else None,
                        "stats": stats,
                        "process_peak_rss": grid["memory"],
                    }
                )
    target = raw["contract"]["primary_target"]
    targets = []
    for name in target["workloads"]:
        row = next(
            (
                row
                for row in rows
                if row["workload"] == name and row["capacity_count"] == target["capacity_count"]
            ),
            None,
        )
        measured = row["speedup_lru_over_compact"] if row else None
        targets.append(
            {
                "workload": name,
                "metric": target["metric"],
                "minimum": target["minimum"],
                "measured": measured,
                "status": "not run"
                if measured is None
                else "met"
                if measured >= target["minimum"]
                else "not met",
            }
        )
    memory_target = raw["contract"]["memory_target"]
    match = next((row for row in memory if row["workload"] == memory_target["workload"]), None)
    measured = match["slots_ratio"] if match else None
    targets.append(
        {
            "workload": memory_target["workload"],
            "metric": memory_target["metric"],
            "maximum": memory_target["maximum"],
            "measured": measured,
            "status": "not run"
            if measured is None
            else "met"
            if measured <= memory_target["maximum"]
            else "not met",
        }
    )
    return {
        "schema_version": 1,
        "run_id": raw["run_id"],
        "implementation": raw["implementation"],
        "environment": raw["environment"],
        "started_at_utc": raw["started_at_utc"],
        "raw_status": raw["status"],
        "quick": raw["quick"],
        "rows": rows,
        "memory": memory,
        "targets": targets,
        "failures": failures,
    }


def number(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def table(summary: dict[str, Any], lang: str) -> str:
    chinese = lang == "zh"
    lines = [
        (
            "实际分析时间；每个方法五次重复的中位数（括号为 compact 最小–最大值）。"
            " 加速比为 LRU / compact；小于 1 表示较慢。"
            if chinese
            else "Measured analysis time: median of five repetitions per method "
            "(compact min–max in parentheses). Speedup is LRU / compact; below 1 is slower."
        ),
        "",
        (
            "| 工作负载 | 容量数 | Compact ms（范围） | Unbounded ms | LRU ms | 加速比 | 状态 |"
            if chinese
            else "| Workload | Capacities | Compact ms (range) | Unbounded ms | LRU ms | Speedup | Status |"
        ),
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in summary["rows"]:
        compact = (
            f"{number(row['compact_median_ms'])} "
            f"({number(row['compact_min_ms'])}–{number(row['compact_max_ms'])})"
        )
        lines.append(
            f"| {row['workload']} | {row['capacity_count']} | {compact} | "
            f"{number(row['unbounded_median_ms'])} | {number(row['lru_median_ms'])} | "
            f"{number(row['speedup_lru_over_compact'])}× | {row['status']} |"
        )
    lines += [
        "",
        "| "
        + (
            "预设目标 | Target | Measured | 结论"
            if chinese
            else "Frozen target | Target | Measured | Outcome"
        )
        + " |",
        "|---|---:|---:|---|",
    ]
    for item in summary["targets"]:
        bound = f">= {item['minimum']:.2f}×" if "minimum" in item else f"<= {item['maximum']:.2f}"
        status = item["status"]
        if chinese:
            status = {"met": "达标", "not met": "未达标", "not run": "未执行"}[status]
        lines.append(f"| {item['workload']} | {bound} | {number(item['measured'], 4)} | {status} |")
    lines += [
        "",
        (
            "内存目标统计 Fenwick 已分配槽位比例，与进程峰值 RSS 分开。"
            if chinese
            else "The memory target counts allocated Fenwick slots, separately from process peak RSS."
        ),
    ]
    env = summary["environment"]
    lines += [
        "",
        f"{env['cpu'] or env['architecture']} · {env['os']} {env['os_release']} · "
        f"Python {env['python']} · 1 thread · run `{summary['run_id']}`.",
        "",
    ]
    if summary["failures"]:
        lines.append(("失败记录：" if chinese else "Failures: ") + json.dumps(summary["failures"]))
    return "\n".join(lines)


def draw(summary: dict[str, Any], destination: Path) -> None:
    """Use matplotlib for a shareable static figure / 使用 matplotlib 输出可分享图表。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = list(dict.fromkeys(row["workload"] for row in summary["rows"]))
    counts = sorted({row["capacity_count"] for row in summary["rows"]})
    figure, axis = plt.subplots(figsize=(12, 6))
    width = 0.8 / max(len(counts), 1)
    for index, count in enumerate(counts):
        values = []
        positions = []
        for group, name in enumerate(names):
            row = next(
                row
                for row in summary["rows"]
                if row["workload"] == name and row["capacity_count"] == count
            )
            if row["speedup_lru_over_compact"] is not None:
                values.append(row["speedup_lru_over_compact"])
                positions.append(group - 0.4 + width / 2 + index * width)
        axis.bar(positions, values, width=width, label=f"{count} capacities")
    if counts:
        axis.set_yscale("log")
    else:
        axis.text(
            0.5,
            0.5,
            "No successful workloads; see raw failure records",
            transform=axis.transAxes,
            ha="center",
        )
    axis.axhline(1, color="#222222", linewidth=1)
    axis.axhline(
        2, color="#666666", linestyle="--", linewidth=0.8, label="2× target (A/B 2048, 64)"
    )
    axis.set_ylabel("Analysis speedup: median finite-LRU time / compact time")
    axis.set_xticks(range(len(names)), names, rotation=28, ha="right")
    axis.set_title("PrefixScope: one core, identical traces and capacities, five repeats")
    axis.grid(axis="y", alpha=0.2)
    axis.set_axisbelow(True)
    axis.legend(fontsize=8)
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(destination, metadata={"Date": None})
    plt.close(figure)


def update_readme(path: Path, content: str) -> None:
    if not path.exists():
        return
    current = path.read_text()
    start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
    if start in current and end in current:
        before, rest = current.split(start, 1)
        _, after = rest.split(end, 1)
        path.write_text(before + start + "\n\n" + content + "\n" + end + after)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        default=ROOT / "results/benchmark.json",
        help="Raw benchmark JSON / 原始基准 JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results",
        help="Tables/summary directory / 表格与摘要目录",
    )
    parser.add_argument(
        "--plot", type=Path, default=ROOT / "assets/benchmark.svg", help="SVG figure / SVG 图表"
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Replace result markers in both READMEs / 更新双语 README 结果标记",
    )
    args = parser.parse_args()
    try:
        summary = summarize(json.loads(args.input.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Analysis error / 分析错误: {error}\n")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for lang, name in (("en", "README.md"), ("zh", "README_zh.md")):
        content = table(summary, lang)
        (args.output_dir / f"table.{lang}.md").write_text(content)
        if args.update_readme:
            update_readme(ROOT / name, content)
    draw(summary, args.plot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
