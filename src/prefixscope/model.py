"""Validated request representation. / 经过验证的请求表示。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Request:
    """Full prefix-page IDs and token count. / 完整前缀页标识与输入 token 数。

    IDs must encode both namespace and preceding prefix; equal IDs must mean
    interchangeable pages. A request cannot repeat an ID. Incomplete tail tokens
    count in the denominator but cannot be reused.
    标识必须包含命名空间及前置前缀；相同标识必须代表可互换的页。请求内不能
    重复标识。不完整尾页计入输入 token 总量，但不计入可复用量。
    """

    blocks: tuple[str, ...]
    input_tokens: int
    block_size: int = 16

    def __post_init__(self) -> None:
        if not isinstance(self.blocks, tuple):
            raise TypeError("blocks must be a tuple / blocks 必须为元组")
        if type(self.input_tokens) is not int or self.input_tokens < 0:
            raise ValueError(
                "input_tokens must be a nonnegative integer / 输入 token 数须为非负整数"
            )
        if type(self.block_size) is not int or self.block_size < 1:
            raise ValueError("block_size must be a positive integer / 页大小须为正整数")
        if len(self.blocks) != self.input_tokens // self.block_size:
            raise ValueError(
                "blocks must represent every complete input page / blocks 必须表示全部完整输入页"
            )
        if any(not isinstance(block, str) or not block for block in self.blocks):
            raise ValueError("block IDs must be nonempty strings / 页标识须为非空字符串")
        if len(set(self.blocks)) != len(self.blocks):
            raise ValueError(
                "block IDs must be unique within each request / 请求内部的页标识须唯一"
            )


def validate_capacities(capacities: object) -> list[int]:
    """Validate ordered capacities, retaining duplicates. / 验证容量并保留顺序及重复项。"""
    from collections.abc import Sequence

    if not isinstance(capacities, Sequence) or isinstance(capacities, (str, bytes)):
        raise TypeError("capacities must be a sequence / 容量须为序列")
    result: list[int] = []
    for capacity in capacities:
        if type(capacity) is not int or capacity < 0:
            raise ValueError("capacities must be nonnegative integers / 容量须为非负整数")
        result.append(capacity)
    return result
