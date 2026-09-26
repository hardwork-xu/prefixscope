"""Bounded JSONL ingestion and prefix identities. / 有边界的 JSONL 读取与前缀标识。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from .model import Request

MAX_LINE_BYTES = 16 * 1024 * 1024
MAX_PAGES = 100_000


def _integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer / 必须是非负整数")
    return value


def chain_blocks(ids: Sequence[int], *, namespace: str, block_size: int = 16) -> tuple[str, ...]:
    """Chain content IDs with their parent and namespace. / 将内容标识与父前缀及命名空间链接。

    Namespace must identify model, tokenizer, adapter, dtype and tenant whenever those
    differ. It is an identity boundary, not encryption. / 不同模型、分词器、适配器、精度或租户
    必须使用不同命名空间；它是身份边界，并非加密。
    """
    if not isinstance(namespace, str) or not namespace or len(namespace) > 1024:
        raise ValueError("namespace must contain 1..1024 characters / 命名空间须为1至1024字符")
    if type(block_size) is not int or block_size <= 0:
        raise ValueError("block_size must be positive / 块大小必须为正整数")
    if len(ids) > MAX_PAGES:
        raise ValueError("too many blocks in one request / 单请求块数量超限")
    parent = hashlib.sha256(
        json.dumps(["prefixscope-v1", namespace, block_size], ensure_ascii=False).encode()
    ).digest()
    blocks = []
    for item in ids:
        raw = str(_integer(item, "block ID / 块标识")).encode("ascii")
        parent = hashlib.sha256(parent + len(raw).to_bytes(4, "big") + raw).digest()
        blocks.append(parent.hex())
    return tuple(blocks)


def from_tokens(tokens: Sequence[int], *, namespace: str, block_size: int = 16) -> Request:
    """Hash complete token blocks; retain tail in denominator. / 散列完整词元块，分母保留尾部。"""
    if type(block_size) is not int or block_size <= 0:
        raise ValueError("block_size must be positive / 块大小必须为正整数")
    if len(tokens) // block_size > MAX_PAGES:
        raise ValueError("too many tokens / 词元数量超限")
    checked = [_integer(t, "token / 词元") for t in tokens]
    ids = [
        int.from_bytes(
            hashlib.sha256(json.dumps(checked[i : i + block_size]).encode()).digest(), "big"
        )
        for i in range(0, len(checked) - block_size + 1, block_size)
    ]
    return Request(
        chain_blocks(ids, namespace=namespace, block_size=block_size), len(tokens), block_size
    )


def _decode(record: Any, format: str, namespace: str) -> Request:
    if not isinstance(record, dict):
        raise ValueError("record must be an object / 每行必须是对象")
    if format == "qwen":
        length = _integer(record.get("input_length"), "input_length")
        ids = record.get("hash_ids")
        if not isinstance(ids, list) or len(ids) < length // 16:
            raise ValueError("hash_ids shorter than complete blocks / 块标识少于完整块数")
        blocks = chain_blocks(ids[: length // 16], namespace=namespace, block_size=16)
        return Request(blocks, length, 16)
    if format == "tokens":
        tokens = record.get("token_ids")
        if not isinstance(tokens, list):
            raise ValueError("token_ids must be an array / 词元必须是数组")
        return from_tokens(tokens, namespace=namespace, block_size=record.get("block_size", 16))
    if format != "native":
        raise ValueError("unknown trace format / 未知轨迹格式")
    if set(record) - {"blocks", "input_tokens", "block_size"}:
        raise ValueError("unknown native field / 原生格式存在未知字段")
    native_blocks = record.get("blocks")
    if not isinstance(native_blocks, list) or len(native_blocks) > MAX_PAGES:
        raise ValueError("blocks must be a bounded array / 块必须为有界数组")
    return Request(
        tuple(native_blocks),
        _integer(record.get("input_tokens"), "input_tokens"),
        record.get("block_size", 16),
    )


def load_jsonl(
    path: str | Path,
    *,
    format: str = "native",
    limit: int | None = None,
    namespace: str = "default",
    max_line_bytes: int = MAX_LINE_BYTES,
) -> Iterator[Request]:
    """Stream validated records; errors include 1-based line number. / 流式校验，错误含行号。

    Qwen: first floor(input_length/16) content hashes, chained with namespace; no
    generated output pages. Order is exactly file order. / Qwen仅保留完整输入块并链式散列，
    不插入生成输出块，严格保留文件顺序。
    """
    if format not in {"native", "qwen", "tokens"}:
        raise ValueError("unknown trace format / 未知轨迹格式")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be nonnegative / 数量限制必须非负")
    if type(max_line_bytes) is not int or max_line_bytes < 1:
        raise ValueError("max_line_bytes must be positive / 行字节限制必须为正")
    with Path(path).open("rb") as stream:
        number = 0
        while limit is None or number < limit:
            raw = stream.readline(max_line_bytes + 1)
            if not raw:
                break
            number += 1
            try:
                if len(raw) > max_line_bytes:
                    raise ValueError("line size limit exceeded / 行大小超限")
                yield _decode(json.loads(raw), format, namespace)
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError(f"line / 行 {number}: {exc}") from exc
