"""Exact request-prefix reuse curves. / 精确的请求前缀复用曲线。"""

import math
from collections.abc import Sequence

from .model import Request, validate_capacities
from .rank import RankIndex


class ResourceLimitError(ValueError):
    """A request would exceed the unique-page budget. / 请求将超出不同页数的预算。"""


class Profile:
    """Analyze serial, completed requests at all cache capacities in one pass.

    一次遍历分析顺序完成的请求在全部缓存容量下的复用情况。
    Pages are checked together at request entry, then touched left to right.
    No TTL, concurrent pinning, output insertion, or variable-sized pages.
    请求进入时统一查询所有页，再从左到右更新访问顺序。不包含 TTL、并发固定页、
    输出插入或不同大小的页。不保留请求历史；状态随不同页数和阈值数增长。
    """

    def __init__(
        self, max_unique_pages: int = 2_000_000, compact: bool = True, initial_slots: int = 1024
    ) -> None:
        if type(max_unique_pages) is not int or max_unique_pages < 1:
            raise ValueError("max_unique_pages must be positive / 不同页数上限须为正整数")
        if type(initial_slots) is not int or initial_slots < 1:
            raise ValueError("initial_slots must be positive / 初始槽位数须为正整数")
        if type(compact) is not bool:
            raise TypeError("compact must be bool / compact 须为布尔值")
        self.max_unique_pages = max_unique_pages
        self.compact = compact
        self.initial_slots = initial_slots
        self.clear()

    def clear(self) -> None:
        """Reset rank state, measurements and page size. / 清空排名、测量值及页大小。"""
        self._index = RankIndex(compact=self.compact, initial_slots=self.initial_slots)
        self._histogram: dict[int, int] = {}
        self._block_size: int | None = None
        self._requests = 0
        self._measured_requests = 0
        self._accesses = 0
        self._total_tokens = 0

    def observe(self, request: Request, *, measure: bool = True) -> tuple[int | None, ...]:
        """Return cumulative pre-request rank thresholds; None means never reusable.

        返回请求进入时排名的前缀最大值；None 表示任何容量下都无法复用。
        ``measure=False`` updates cache state but excludes this request's tokens.
        Invalid input and unique-page limit rejection leave all state unchanged.
        ``measure=False`` 更新缓存状态但不计入该请求的 token；非法输入及页数预算
        拒绝均不改变已有状态。每次请求的页大小必须一致。
        Allocation failure is not transactional. / 内存分配失败不保证事务回滚。
        """
        if not isinstance(request, Request):
            raise TypeError("request must be Request / request 须为 Request")
        if type(measure) is not bool:
            raise TypeError("measure must be bool / measure 须为布尔值")
        if self._block_size is not None and request.block_size != self._block_size:
            raise ValueError("block_size must remain constant / 所有请求须使用相同页大小")
        unseen = sum(block not in self._index.positions for block in request.blocks)
        if len(self._index.positions) + unseen > self.max_unique_pages:
            raise ResourceLimitError("unique-page budget exceeded / 超出不同页数预算")

        thresholds: list[int | None] = []
        required = 0
        cold_prefix = False
        # All reads precede all writes: a request cannot evict its own prefix
        # during lookup. / 全部读取先于写入，避免请求查询时淘汰自身前缀。
        for block in request.blocks:
            rank = self._index.rank(block)
            if rank is None:
                cold_prefix = True
            elif not cold_prefix:
                required = max(required, rank)
            threshold = None if cold_prefix else required
            thresholds.append(threshold)
            if measure and threshold is not None:
                self._histogram[threshold] = self._histogram.get(threshold, 0) + request.block_size
        for block in request.blocks:
            self._index.touch(block)
        self._block_size = request.block_size
        self._requests += 1
        self._accesses += len(request.blocks)
        if measure:
            self._measured_requests += 1
            self._total_tokens += request.input_tokens
        return tuple(thresholds)

    def curve(self, capacities: Sequence[int]) -> list[dict[str, int | float]]:
        """Return exact token reuse in input order. / 按输入顺序返回精确 token 复用量。

        Empty measured input has hit_rate=0. Duplicate capacities are retained.
        没有测量 token 时 hit_rate 为 0；重复容量会保留。
        """
        checked = validate_capacities(capacities)
        histogram = sorted(self._histogram.items())
        reused_by_capacity: dict[int, int] = {}
        position = 0
        reused = 0
        for capacity in sorted(set(checked)):
            while position < len(histogram) and histogram[position][0] <= capacity:
                reused += histogram[position][1]
                position += 1
            reused_by_capacity[capacity] = reused
        return [
            {
                "capacity_pages": capacity,
                "reused_tokens": reused_by_capacity[capacity],
                "total_tokens": self._total_tokens,
                "hit_rate": (
                    reused_by_capacity[capacity] / self._total_tokens if self._total_tokens else 0.0
                ),
            }
            for capacity in checked
        ]

    def minimum_capacity(self, target_hit_rate: float) -> int | None:
        """Smallest page capacity reaching a target, or None if unattainable.

        返回达到目标命中率的最小页容量；不可达时返回 None；目标为 0 时返回 0。
        Target must be a finite number in [0, 1]. / 目标须为 [0, 1] 内有限数值。
        """
        if (
            isinstance(target_hit_rate, bool)
            or not isinstance(target_hit_rate, (int, float))
            or not 0 <= target_hit_rate <= 1
            or not math.isfinite(target_hit_rate)
        ):
            raise ValueError("target_hit_rate must lie in [0, 1] / 目标命中率须在 [0, 1] 内")
        if target_hit_rate == 0:
            return 0
        if self._total_tokens == 0:
            return None
        reused = 0
        for capacity, tokens in sorted(self._histogram.items()):
            reused += tokens
            if reused / self._total_tokens >= target_hit_rate:
                return capacity
        return None

    def stats(self) -> dict[str, int]:
        """Return counters and structural slots, not RSS. / 返回计数及结构槽位数，非 RSS。

        ``accesses`` and ``requests`` include warmup; other token/request counters
        include only measured requests. allocated_slots excludes the unused zero
        element in the signed-64-bit Fenwick array.
        accesses 和 requests 包括预热；token 及 measured_requests 只含测量请求。
        allocated_slots 不含 64 位有符号整数 Fenwick 数组未使用的下标 0 元素。
        """
        return {
            "unique_pages": len(self._index.positions),
            "allocated_slots": self._index.slots,
            "compactions": self._index.compactions,
            "accesses": self._accesses,
            "requests": self._requests,
            "measured_requests": self._measured_requests,
            "total_tokens": self._total_tokens,
        }
