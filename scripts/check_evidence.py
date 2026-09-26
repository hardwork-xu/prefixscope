"""Validate measured evidence against the current implementation. / 对当前实现校验实测证据。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("benchmark", ROOT / "benchmark.py")
assert spec and spec.loader
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def main() -> None:
    raw = json.loads((ROOT / "results/benchmark.json").read_text())
    assert raw["schema_version"] == 1 and raw["status"] == "passed" and raw["quick"] is False
    assert raw["implementation"]["source_sha256"] == benchmark.source_version()["source_sha256"]
    assert raw["contract"] == json.loads((ROOT / "experiments/contract.json").read_text())
    assert len(raw["workloads"]) == 8
    samples = warmups = 0
    for workload in raw["workloads"]:
        assert workload["status"] == "passed"
        for grid in workload["grids"]:
            assert len(grid["samples"]) == 15 and len(grid["warmups"]) == 3
            for sample in grid["samples"] + grid["warmups"]:
                assert sample["status"] == "passed" and sample["correct"] is True
                assert sample["duration_ns"] > 0
            for method in ("compact", "unbounded", "lru"):
                selected = [s for s in grid["samples"] if s["method"] == method]
                assert sorted(s["iteration"] for s in selected) == list(range(5))
            samples += len(grid["samples"])
            warmups += len(grid["warmups"])
            for item in grid.get("memory", {}).values():
                assert item["status"] == "passed" and item["peak_rss_bytes"] > 0
    assert (samples, warmups) == (360, 72)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": raw["run_id"],
                "samples": samples,
                "warmups": warmups,
                "source_sha256": raw["implementation"]["source_sha256"],
                "evidence": "results/benchmark.json",
                "execution_command": raw["command"],
                "started_at_utc": raw["started_at_utc"],
                "finished_at_utc": raw["finished_at_utc"],
            }
        )
    )


if __name__ == "__main__":
    main()
