"""Scan tracked/public project files for common accidental disclosures. / 扫描常见意外泄漏。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
    ).stdout
    paths = [ROOT / name.decode() for name in tracked.split(b"\0") if name]
    patterns = [
        r"/(?:Users|home)/[A-Za-z0-9_.-]+/",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}",
        r"\bsk-[A-Za-z0-9]{24,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"[A-Za-z0-9_.+-]+@(?:gmail|outlook|qq)\.com",
    ]
    failures = []
    for path in paths:
        if not path.is_file():
            failures.append(f"missing tracked file: {path.relative_to(ROOT)}")
            continue
        if path.suffix in {".png", ".pdf", ".whl", ".gz", ".zip"}:
            continue
        text = path.read_text(errors="replace")
        for pattern in patterns:
            if re.search(pattern, text):
                failures.append(f"sensitive-pattern match: {path.relative_to(ROOT)}")
    assert not failures, failures
    print(
        json.dumps(
            {
                "status": "passed",
                "tracked_files": len(paths),
                "scope": "common patterns, not a proof that arbitrary private data is absent",
            }
        )
    )


if __name__ == "__main__":
    main()
