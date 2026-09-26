#!/usr/bin/env python3
"""Plot measured capacity curves and memory / 绘制实测容量曲线与内存图。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"compact": "#0072B2", "unbounded": "#E69F00", "lru": "#777777"}


def grid64(workload: dict[str, Any]) -> dict[str, Any]:
    """Select measured 64-capacity evidence / 选择已测量的64容量证据。"""
    for grid in workload["grids"]:
        if grid["capacity_count"] == 64:
            if not all(method["status"] == "passed" for method in grid["methods"].values()):
                raise ValueError("Cannot plot failed method as valid / 不能将失败方法绘为有效结果")
            return grid
    raise ValueError("64-capacity experiment missing / 缺少64容量实验")


def create_plots(raw: dict[str, Any], directory: Path) -> None:
    """Read raw values without re-running analyzers / 仅读取原始结果，不重新运行分析器。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if raw.get("schema_version") != 1 or raw.get("quick"):
        raise ValueError("Full schema-v1 benchmark required / 需要完整的版本1基准结果")
    by_name = {item["spec"]["name"]: item for item in raw["workloads"]}
    selected = [by_name[f"qwen_trace{trace}_2048"] for trace in ("A", "B")]
    directory.mkdir(parents=True, exist_ok=True)

    figure, axis = plt.subplots(figsize=(10, 5.4))
    for workload in selected:
        curve = grid64(workload)["reference_curve"]
        x = [row["capacity_pages"] for row in curve]
        y = [row["hit_rate"] * 100 for row in curve]
        if x != sorted(x) or y != sorted(y):
            raise ValueError("Capacity curve must be monotone / 容量曲线必须单调")
        axis.plot(x, y, linewidth=2, label=workload["spec"]["name"])
    axis.set_xlabel("Cache capacity (16-token pages)")
    axis.set_ylabel("Reusable input tokens / all input tokens (%)")
    axis.set_ylim(bottom=0)
    axis.set_title("Exact serial page-LRU prefix reuse on public Qwen trace subsets")
    axis.grid(alpha=0.25)
    axis.legend()
    figure.text(
        0.5,
        0.02,
        "Every analysis starts empty; all 2,048 requests count. Trace warmup: 0 requests.\n"
        "Timing warmup: one separate full analysis, discarded. Incomplete tail tokens cannot hit.",
        ha="center",
        fontsize=9,
    )
    figure.tight_layout(rect=(0, 0.1, 1, 1))
    figure.savefig(directory / "capacity-curves.svg", metadata={"Date": None})
    plt.close(figure)

    figure, (slots_axis, rss_axis) = plt.subplots(
        1, 2, figsize=(15, 6.5), gridspec_kw={"width_ratios": [1, 3]}
    )
    hot = grid64(by_name["hot_loop_20000"])
    slot_methods = ("compact", "unbounded")
    slots = [
        next(
            sample["stats"]["allocated_slots"]
            for sample in hot["samples"]
            if sample["method"] == method and sample["status"] == "passed"
        )
        for method in slot_methods
    ]
    slots_axis.bar(slot_methods, slots, color=[COLORS[method] for method in slot_methods])
    for index, count in enumerate(slots):
        slots_axis.annotate(
            f"{count:,}",
            (index, count),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )
    slots_axis.set_yscale("log")
    slots_axis.set_ylim(top=max(slots) * 3)
    slots_axis.set_ylabel("Allocated Fenwick slots (log scale)")
    slots_axis.set_title("Structural array state\nhot_loop_20000")
    slots_axis.grid(axis="y", alpha=0.2)
    slots_axis.set_axisbelow(True)

    workloads = raw["workloads"]
    width = 0.25
    for method_index, method in enumerate(("compact", "unbounded", "lru")):
        rss_values = []
        for workload in workloads:
            measurement = grid64(workload)["memory"][method]
            if measurement["status"] != "passed":
                raise ValueError("RSS measurement failed / RSS 测量失败")
            rss_values.append(measurement["peak_rss_bytes"] / 1024**2)
        positions = [index + (method_index - 1) * width for index in range(len(workloads))]
        rss_axis.bar(positions, rss_values, width, color=COLORS[method], label=method)
    rss_axis.set_xticks(
        range(len(workloads)),
        [workload["spec"]["name"] for workload in workloads],
        rotation=30,
        ha="right",
    )
    rss_axis.set_ylabel("Peak process RSS (MiB)")
    rss_axis.set_title("Independent process memory: runtime + inputs + analyzer\n64 capacities")
    rss_axis.grid(axis="y", alpha=0.2)
    rss_axis.set_axisbelow(True)
    rss_axis.legend()
    figure.text(
        0.5,
        0.02,
        "Left: structural slot count, excludes unused index 0; this is not RSS. "
        "Right: one fresh subprocess per workload/method; no variance claim.",
        ha="center",
        fontsize=9,
    )
    figure.tight_layout(rect=(0, 0.09, 1, 1))
    figure.savefig(directory / "memory.svg", metadata={"Date": None})
    plt.close(figure)


def captions(raw: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    texts = {
        "en": (
            "# Figure captions\n\n"
            "**Capacity curves.** Public Qwen A/B subsets, first 2,048 records in original order; "
            "64 capacities from 64 to 16,192 full 16-token pages. Every analysis begins with "
            "an empty cache and measures every request. Trace warmup is zero; the single "
            "discarded timing warmup is a separate full analysis. The token-weighted rate "
            "includes incomplete tail tokens in the denominator. Curves are finite-LRU "
            "reference values, exactly matched by both profiler variants. They describe "
            "the declared serial cache model, not measured inference latency.\n\n"
            "**Memory.** The left panel reports allocated Fenwick slots on the synthetic "
            "20,000-request hot loop, excluding unused index zero. The right panel reports "
            "measured process peak RSS in MiB for one fresh subprocess per workload/method "
            "with 64 capacities, including Python, input loading/normalization and the "
            "analyzer. Structural counts and RSS are different quantities. RSS has one "
            "sample per condition; no statistical memory-reduction claim follows.\n\n"
        ),
        "zh": (
            "# 图表说明\n\n"
            "**容量曲线。** 使用公开 Qwen A/B 各自原始顺序的前2,048条记录；64个容量点从64到16,192页，"
            "每个完整页为16 tokens。每次分析从空缓存开始，全部请求计分；轨迹预热请求数为零。"
            "计时前丢弃的一次预热是独立的完整分析，不改变计分运行的缓存初始状态。"
            "命中率按 token 加权，分母包含不能复用的不完整尾页 tokens。曲线取自有限 LRU 参考实现，"
            "两种分析器均精确一致。这些结果描述约定的串行缓存模型，不是实测模型推理延迟。\n\n"
            "**内存。** 左图给出20,000次请求合成热点循环的 Fenwick 已分配槽位数，不含未使用的下标0。"
            "右图为64容量条件下，每个负载/方法独立新进程的实测峰值 RSS（MiB），包含 Python、"
            "输入读取与归一化及分析器。结构槽位和 RSS 是不同统计量。每个条件仅测量一次 RSS，"
            "不据此声称有统计意义的进程内存下降。\n\n"
        ),
    }
    for language, content in texts.items():
        (directory / f"figures.{language}.md").write_text(
            content + f"Run ID: `{raw['run_id']}`\n", encoding="utf-8"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=ROOT / "results/benchmark.json",
        help="Full raw benchmark JSON / 完整原始基准JSON",
    )
    parser.add_argument(
        "--asset-dir", type=Path, default=ROOT / "assets", help="Figure directory / 图表目录"
    )
    parser.add_argument(
        "--caption-dir",
        type=Path,
        default=ROOT / "results",
        help="Bilingual caption directory / 双语说明目录",
    )
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text())
        create_plots(raw, args.asset_dir)
        captions(raw, args.caption_dir)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"Plot error / 绘图错误: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
