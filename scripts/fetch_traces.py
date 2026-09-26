"""Fetch checksum-pinned public traces. / 下载并校验固定版本的公开轨迹。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

REVISION = "5f7439c51ec248a0c585f7d90a41a6f57773b912"
FILES = {
    "qwen_traceA_blksz_16.jsonl": "07cedc9ed8aff301994ac68ed4aede8123b7603673575eeba9dd677de663db17",
    "qwen_traceB_blksz_16.jsonl": "68e3f98e2d601d60d0abf4b89bc8a3654372abab7b1cde6373a13d0054379d59",
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public Qwen traces / 下载公开Qwen轨迹")
    parser.add_argument("--directory", default="data/raw", help="destination / 目标目录")
    args = parser.parse_args()
    directory = Path(args.directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        path = directory / name
        if path.exists() and digest(path) == expected:
            print(f"verified / 已校验: {name}")
            continue
        url = f"https://media.githubusercontent.com/media/alibaba-edu/qwen-bailian-usagetraces-anon/{REVISION}/{name}"
        temporary = path.with_suffix(".download")
        subprocess.run(
            [
                "curl",
                "--fail",
                "--location",
                "--retry",
                "3",
                "--max-time",
                "300",
                "--output",
                str(temporary),
                url,
            ],
            check=True,
        )
        actual = digest(temporary)
        if actual != expected:
            raise ValueError(f"checksum mismatch / 校验失败: {name}; received {actual}")
        temporary.replace(path)
        print(json.dumps({"file": name, "sha256": actual, "bytes": path.stat().st_size}))


if __name__ == "__main__":
    main()
