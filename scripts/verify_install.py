"""Verify locked install and wheel in a fresh environment. / 在干净环境验证锁定安装和wheel。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    wheels = sorted((ROOT / "dist").glob("prefixscope-0.1.0-*.whl"))
    if len(wheels) != 1:
        raise ValueError("build exactly one wheel first / 请先构建唯一wheel")
    with tempfile.TemporaryDirectory(prefix="prefixscope-clean-") as directory:
        env = Path(directory)
        venv.EnvBuilder(with_pip=True).create(env)
        python = str(env / "bin/python")
        commands = [
            [
                python,
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "-r",
                str(ROOT / "requirements.lock"),
            ],
            [python, "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])],
            [
                python,
                "-c",
                "from prefixscope import Profile,Request; p=Profile(); p.observe(Request(('a',),16)); assert p.curve([1])[0]['total_tokens']==16",
            ],
            [python, "-m", "prefixscope", "demo"],
            [
                python,
                "-m",
                "prefixscope",
                "analyze",
                str(ROOT / "examples/tokens.jsonl"),
                "--format",
                "tokens",
                "--capacities",
                "0,4,5,16,64",
            ],
            [python, "-m", "pip", "check"],
        ]
        for index, command in enumerate(commands):
            process = subprocess.run(command, cwd=env, capture_output=True, text=True)
            shown = [
                arg.replace(str(env), "<clean-env>").replace(str(ROOT), ".") for arg in command
            ]
            print(json.dumps({"step": index, "command": shown, "exit_code": process.returncode}))
            if process.returncode:
                detail = (
                    (process.stdout + process.stderr)[-3000:]
                    .replace(str(env), "<clean-env>")
                    .replace(str(ROOT), ".")
                )
                raise RuntimeError(detail)
            if index == 3:
                assert json.loads(process.stdout)["status"] == "passed"
        print("Clean environment and installed wheel passed / 干净环境与已安装wheel验证通过")


if __name__ == "__main__":
    main()
