"""Command-line interface. / 命令行接口。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn

from .profiler import Profile
from .reference import replay
from .trace import from_tokens, load_jsonl


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        super().error(f"{message} / 参数错误，请查看 --help")


def _capacities(value: str) -> list[int]:
    try:
        result = [int(x) for x in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("comma-separated integers / 逗号分隔整数") from exc
    if not result or any(x < 0 for x in result):
        raise argparse.ArgumentTypeError("capacities must be nonnegative / 容量必须非负")
    return result


def _write(value: dict[str, Any], path: str | None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path is None:
        print(text, end="")
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, delete=False
        ) as f:
            name = f.name
            f.write(text)
        os.replace(name, target)
    finally:
        if name is not None and Path(name).exists():
            Path(name).unlink()


def main(argv: list[str] | None = None) -> int:
    """Run offline analysis; return 0 or diagnostic status 2. / 运行离线分析，返回0或错误码2。"""
    parser = Parser(description="Prefix-cache capacity analysis / 前缀缓存容量分析")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="offline verified example / 离线完整示例")
    analyze = commands.add_parser("analyze", help="analyze a JSONL trace / 分析JSONL轨迹")
    analyze.add_argument("input", help="input JSONL path / 输入文件")
    analyze.add_argument(
        "--format",
        choices=["native", "qwen", "tokens"],
        default="native",
        help="input schema / 输入格式",
    )
    analyze.add_argument(
        "--namespace", default="default", help="model and tenant identity / 模型租户身份"
    )
    analyze.add_argument(
        "--capacities",
        type=_capacities,
        default=[0, 64, 256, 1024, 4096],
        help="cache pages, comma-separated / 逗号分隔的缓存页数",
    )
    analyze.add_argument("--limit", type=int, help="first N requests / 前N条请求")
    analyze.add_argument(
        "--warmup", type=int, default=0, help="state-only initial requests / 仅预热的请求数"
    )
    analyze.add_argument(
        "--max-unique", type=int, default=2_000_000, help="distinct-page limit / 不同页数量上限"
    )
    analyze.add_argument(
        "--target", type=float, default=0.5, help="target token hit rate in [0,1] / 目标词元命中率"
    )
    analyze.add_argument(
        "--output", help="atomic JSON output; default stdout / 原子写入JSON，默认标准输出"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            requests = [from_tokens(list(range(64)) + [i] * 16, namespace="demo") for i in range(8)]
            profile = Profile()
            for request in requests:
                profile.observe(request)
            curve = profile.curve([0, 4, 5, 16, 64])
            if curve != replay(requests, [0, 4, 5, 16, 64]):
                raise ValueError("reference mismatch / 与参考实现不一致")
            _write(
                {
                    "schema_version": 1,
                    "status": "passed",
                    "data_kind": "synthetic",
                    "semantics": "serial-request-entry-lru",
                    "curve": curve,
                    "stats": profile.stats(),
                },
                None,
            )
            return 0
        if args.warmup < 0:
            raise ValueError("warmup must be nonnegative / 预热数必须非负")
        profile = Profile(max_unique_pages=args.max_unique)
        count = 0
        for count, request in enumerate(
            load_jsonl(args.input, format=args.format, limit=args.limit, namespace=args.namespace),
            1,
        ):
            profile.observe(request, measure=count > args.warmup)
        if args.warmup > count:
            raise ValueError("warmup exceeds request count / 预热数超过请求数")
        result = {
            "schema_version": 1,
            "semantics": "serial-request-entry-lru",
            "curve": profile.curve(args.capacities),
            "stats": profile.stats(),
            "target_hit_rate": args.target,
            "minimum_capacity_pages": profile.minimum_capacity(args.target),
        }
        _write(result, args.output)
        return 0
    except (ValueError, OSError, TypeError, OverflowError) as exc:
        print(f"error / 错误: {exc}", file=sys.stderr)
        return 2
