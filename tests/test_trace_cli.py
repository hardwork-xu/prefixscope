from __future__ import annotations

import json
import subprocess
import sys

import pytest

from prefixscope.trace import chain_blocks, from_tokens, load_jsonl


def test_parent_and_namespace_isolation():
    assert chain_blocks([1, 3], namespace="a")[1] != chain_blocks([2, 3], namespace="a")[1]
    assert chain_blocks([1], namespace="a") != chain_blocks([1], namespace="b")
    assert chain_blocks([1], namespace="a", block_size=16) != chain_blocks(
        [1], namespace="a", block_size=8
    )
    assert len(set(chain_blocks([1, 1, 1], namespace="a"))) == 3


def test_tokens_tail():
    first = from_tokens(list(range(18)), namespace="test", block_size=8)
    second = from_tokens(list(range(16)) + [99, 100], namespace="test", block_size=8)
    assert first.blocks == second.blocks
    assert first.input_tokens == 18
    assert len(first.blocks) == 2


@pytest.mark.parametrize("tokens", [[True], [-1], [1.2], ["1"]])
def test_bad_tokens(tokens):
    with pytest.raises(ValueError):
        from_tokens(tokens, namespace="test")


@pytest.mark.parametrize("namespace", ["", "x" * 1025, None])
def test_bad_namespace(namespace):
    with pytest.raises(ValueError):
        chain_blocks([1], namespace=namespace)


def test_qwen_normalization(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text(
        json.dumps({"input_length": 33, "hash_ids": [7, 8, 9], "output_length": 100}) + "\n"
    )
    request = list(load_jsonl(path, format="qwen", namespace="Q"))[0]
    assert request.blocks == chain_blocks([7, 8], namespace="Q")
    assert request.input_tokens == 33
    assert list(load_jsonl(path, format="qwen", limit=0)) == []


@pytest.mark.parametrize(
    "line",
    [
        "",
        "[]",
        '{"blocks":[],"input_tokens":false}',
        '{"blocks":[],"input_tokens":0,"typo":1}',
        '{"blocks":["x"],"input_tokens":0}',
        "{broken",
    ],
)
def test_invalid_lines(tmp_path, line):
    path = tmp_path / "bad.jsonl"
    path.write_text(line + "\n")
    with pytest.raises(ValueError, match="line / 行 1"):
        list(load_jsonl(path))


def test_size_limit_and_decode(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(b"x" * 20 + b"\n")
    with pytest.raises(ValueError, match="size"):
        list(load_jsonl(path, max_line_bytes=10))
    path.write_bytes(b"\xff\n")
    with pytest.raises(ValueError):
        list(load_jsonl(path))


def test_tokens_jsonl_and_native(tmp_path):
    path = tmp_path / "token.jsonl"
    path.write_text(json.dumps({"token_ids": list(range(32)), "block_size": 16}) + "\n")
    request = list(load_jsonl(path, format="tokens"))[0]
    path.write_text(json.dumps({"blocks": list(request.blocks), "input_tokens": 32}) + "\n")
    assert list(load_jsonl(path))[0] == request


@pytest.mark.integration
def test_cli_demo_and_help():
    proc = subprocess.run(
        [sys.executable, "-m", "prefixscope", "demo"], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["status"] == "passed"
    help_result = subprocess.run(
        [sys.executable, "-m", "prefixscope", "analyze", "--help"], capture_output=True, text=True
    )
    assert help_result.returncode == 0
    assert "命中率" in help_result.stdout


@pytest.mark.integration
def test_cli_atomic_output_and_failure(tmp_path):
    path = tmp_path / "in.jsonl"
    path.write_text('{"blocks":["a","b"],"input_tokens":32}\n' * 2)
    output = tmp_path / "out.json"
    cmd = [
        sys.executable,
        "-m",
        "prefixscope",
        "analyze",
        str(path),
        "--capacities",
        "0,1,2",
        "--output",
        str(output),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    value = json.loads(output.read_text())
    assert value["curve"][2]["reused_tokens"] == 32
    before = output.read_bytes()
    path.write_text("malformed\n")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 2
    assert "错误" in proc.stderr
    assert output.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.jsonl", "out.json"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "extra",
    [
        ["--target", "nan"],
        ["--warmup", "-1"],
        ["--warmup", "10"],
        ["--limit", "-1"],
        ["--capacities", "-2"],
    ],
)
def test_cli_rejects_invalid_parameters(tmp_path, extra):
    path = tmp_path / "in.jsonl"
    path.write_text('{"blocks":[],"input_tokens":0}\n')
    proc = subprocess.run(
        [sys.executable, "-m", "prefixscope", "analyze", str(path), *extra],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
