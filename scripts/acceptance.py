"""Run local acceptance and retain sanitized evidence. / 执行本地验收并保留脱敏证据。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark", ROOT / "benchmark.py")
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def record(name: str, command: list[str], directory: Path) -> dict:
    started = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    raw = process.stdout + process.stderr
    clean = benchmark.sanitized(raw).replace(
        str(Path(sys.executable).parent.parent), "<environment>"
    )
    log = directory / f"{name}.log"
    log.write_text(clean)
    return {
        "name": name,
        "command": ["python" if arg == sys.executable else arg for arg in command],
        "started_at_utc": started,
        "duration_seconds": time.perf_counter() - start,
        "status": "passed" if process.returncode == 0 else "failed",
        "exit_code": process.returncode,
        "summary": clean[-1200:],
        "evidence": log.relative_to(ROOT).as_posix(),
        "source": benchmark.source_version(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full-benchmark", action="store_true", help="rerun full benchmark / 重跑完整基准"
    )
    args = parser.parse_args()
    directory = ROOT / "results/acceptance"
    directory.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    commands = [
        (
            "api",
            [
                py,
                "-c",
                "from prefixscope import Profile, Request; p=Profile(); p.observe(Request(('a',),16)); assert p.curve([1])[0]['reused_tokens']==0; print('API passed')",
            ],
        ),
        ("demo", [py, "-m", "prefixscope", "demo"]),
        ("unit", [py, "-m", "pytest", "-m", "not integration", "-q"]),
        ("integration", [py, "-m", "pytest", "-m", "integration", "-q"]),
        ("lint", [py, "-m", "ruff", "check", "src", "tests", "scripts", "benchmark.py"]),
        (
            "format",
            [py, "-m", "ruff", "format", "--check", "src", "tests", "scripts", "benchmark.py"],
        ),
        ("types", [py, "-m", "mypy"]),
        (
            "benchmark",
            [
                py,
                "benchmark.py",
                *([] if args.full_benchmark else ["--quick"]),
                "--output",
                "results/benchmark.json"
                if args.full_benchmark
                else "results/acceptance/smoke.json",
            ],
        ),
        ("full_benchmark_evidence", [py, "scripts/check_evidence.py"]),
        ("analysis", [py, "scripts/analyze_results.py", "results/benchmark.json"]),
        ("build", [py, "-m", "build", "--no-isolation"]),
        ("clean_install", [py, "scripts/verify_install.py"]),
        ("capacity_plot", [py, "scripts/plot_capacity.py", "results/benchmark.json"]),
        ("docs", [py, "scripts/check_docs.py"]),
        ("public", [py, "scripts/check_public.py"]),
        ("diff", ["git", "diff", "--check"]),
    ]
    records = []
    (directory / "checks.json").write_text(
        json.dumps({"schema_version": 1, "status": "running", "checks": records}) + "\n"
    )
    for name, command in commands:
        item = record(name, command, directory)
        records.append(item)
        print(name, item["status"], flush=True)
    if shutil.which("docker"):
        build = record(
            "docker_build", ["docker", "build", "-t", "prefixscope:local", "."], directory
        )
        records.append(build)
        if build["status"] == "passed":
            records.append(
                record(
                    "docker_run", ["docker", "run", "--rm", "prefixscope:local", "demo"], directory
                )
            )
    else:
        for name in ("docker_build", "docker_run"):
            records.append(
                {
                    "name": name,
                    "status": "not_run",
                    "exit_code": None,
                    "command": "docker build -t prefixscope:local ."
                    if name.endswith("build")
                    else "docker run --rm prefixscope:local demo",
                    "summary": "Docker executable absent on local host / 本机没有Docker可执行文件",
                    "evidence": "results/environment.json",
                    "source": benchmark.source_version(),
                }
            )
    payload = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "checks": records,
        "status": "failed"
        if any(r["status"] == "failed" for r in records)
        else "passed_with_unverified_container",
    }
    (directory / "checks.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 1 if payload["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
