"""Independent finite-capacity LRU replay. / 独立的有限容量 LRU 回放。"""

from collections import OrderedDict
from collections.abc import Iterable, Sequence

from .model import Request, validate_capacities


def replay(
    requests: Iterable[Request], capacities: Sequence[int], warmup_requests: int = 0
) -> list[dict[str, int | float]]:
    """Replay each capacity with its own OrderedDict cache. / 每个容量独立回放缓存。

    All prefix membership checks happen at request entry; every page is then
    touched left to right. Warmup changes state but not the token denominator.
    输入时先检查完整前缀，再从左到右访问每页。预热更新状态但不计入 token 分母。
    This oracle does not use ranks, thresholds, or the optimized histogram.
    本参考实现不使用排名、阈值或优化版本的直方图。
    """
    checked = validate_capacities(capacities)
    if type(warmup_requests) is not int or warmup_requests < 0:
        raise ValueError("warmup_requests must be nonnegative / 预热请求数须为非负整数")
    caches: list[OrderedDict[str, None]] = [OrderedDict() for _ in checked]
    reused = [0] * len(checked)
    total_tokens = 0
    block_size: int | None = None
    for number, request in enumerate(requests):
        if not isinstance(request, Request):
            raise TypeError("request must be Request / request 须为 Request")
        if block_size is not None and request.block_size != block_size:
            raise ValueError("block_size must remain constant / 所有请求须使用相同页大小")
        block_size = request.block_size
        measure = number >= warmup_requests
        if measure:
            total_tokens += request.input_tokens
        for index, (capacity, cache) in enumerate(zip(checked, caches, strict=True)):
            if measure:
                for block in request.blocks:
                    if block not in cache:
                        break
                    reused[index] += request.block_size
            for block in request.blocks:
                if capacity == 0:
                    continue
                if block in cache:
                    cache.move_to_end(block)
                else:
                    cache[block] = None
                    if len(cache) > capacity:
                        cache.popitem(last=False)
    return [
        {
            "capacity_pages": capacity,
            "reused_tokens": reused[index],
            "total_tokens": total_tokens,
            "hit_rate": reused[index] / total_tokens if total_tokens else 0.0,
        }
        for index, capacity in enumerate(checked)
    ]
