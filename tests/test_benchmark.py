"""Evidence-pipeline integration tests / 实验证据流程集成测试。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def quick_result(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    path = tmp_path_factory.mktemp("benchmark") / "raw.json"
    process = subprocess.run(
        [sys.executable, "benchmark.py", "--quick", "--output", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    return path, json.loads(path.read_text())


@pytest.mark.integration
def test_benchmark_preserves_repetitions_and_exactness(quick_result: tuple[Path, dict]) -> None:
    _, raw = quick_result
    assert raw["status"] == "passed"
    assert raw["quick"] is True
    assert len(raw["implementation"]["source_sha256"]) == 64
    assert raw["started_at_utc"] < raw["finished_at_utc"]
    assert "/Users/" not in json.dumps(raw)
    assert len(raw["workloads"]) == 2
    for workload in raw["workloads"]:
        assert workload["input"]["data_kind"] == "synthetic"
        assert workload["input"]["loading_and_normalization_ns"] > 0
        for grid in workload["grids"]:
            assert len(grid["warmups"]) == 3
            assert len(grid["samples"]) == 15
            assert sorted(grid["methods"]) == ["compact", "lru", "unbounded"]
            for sample in grid["samples"]:
                assert sample["correct"] is True
                assert sample["duration_ns"] > 0
                assert sample["status"] == "passed"
            for method in grid["methods"].values():
                assert method["samples"] == 5
                assert method["min_ns"] <= method["median_ns"] <= method["max_ns"]
            if "memory" in grid:
                for memory in grid["memory"].values():
                    assert memory["status"] == "passed"
                    assert memory["peak_rss_bytes"] > 0


@pytest.mark.integration
def test_analysis_generates_bilingual_tables_and_plot(
    quick_result: tuple[Path, dict], tmp_path: Path
) -> None:
    raw_path, raw = quick_result
    output = tmp_path / "report"
    plot = tmp_path / "benchmark.svg"
    process = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_results.py",
            str(raw_path),
            "--output-dir",
            str(output),
            "--plot",
            str(plot),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr
    summary = json.loads((output / "summary.json").read_text())
    assert summary["run_id"] == raw["run_id"]
    assert len(summary["rows"]) == 4
    assert all(item["status"] == "not run" for item in summary["targets"])
    for lang in ("en", "zh"):
        table = (output / f"table.{lang}.md").read_text()
        assert "quick_hot_32" in table
        assert "quick_cold_16" in table
        assert raw["run_id"] in table
    assert "<svg" in plot.read_text()


@pytest.mark.integration
def test_benchmark_rejects_invalid_contract(tmp_path: Path) -> None:
    contract = tmp_path / "invalid.json"
    contract.write_text('{"schema_version": 999}')
    output = tmp_path / "unwritten.json"
    process = subprocess.run(
        [sys.executable, "benchmark.py", "--config", str(contract), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 2
    assert "Unsupported contract schema" in process.stderr
    assert "不支持" in process.stderr
    assert not output.exists()


@pytest.mark.integration
def test_analysis_rejects_invalid_schema(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"schema_version": 0}')
    process = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_results.py",
            str(malformed),
            "--output-dir",
            str(tmp_path / "report"),
            "--plot",
            str(tmp_path / "plot.svg"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 2
    assert "Unsupported result schema" in process.stderr
    assert not (tmp_path / "plot.svg").exists()
