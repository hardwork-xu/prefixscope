"""Differential and invariant tests. / 差分及不变量测试。"""

import random
from dataclasses import FrozenInstanceError

import pytest

from prefixscope import Profile, Request, ResourceLimitError, replay
from prefixscope.rank import RankIndex


def request(*blocks: str, tail: int = 0, block_size: int = 16) -> Request:
    return Request(tuple(blocks), len(blocks) * block_size + tail, block_size)


@pytest.mark.parametrize("seed", range(100))
def test_randomized_against_independent_finite_lru(seed: int) -> None:
    rng = random.Random(seed)
    pages = [f"namespace/前缀/{index}" for index in range(20)]
    trace = [
        request(*rng.sample(pages, rng.randrange(11)), tail=rng.randrange(16)) for _ in range(40)
    ]
    capacities = list(range(26)) + [4, 1, 4]
    rng.shuffle(capacities)
    warmup = seed % 5
    optimized = Profile(initial_slots=4)
    unbounded = Profile(initial_slots=4, compact=False)
    for index, item in enumerate(trace):
        thresholds = optimized.observe(item, measure=index >= warmup)
        assert thresholds == unbounded.observe(item, measure=index >= warmup)
        finite = [threshold for threshold in thresholds if threshold is not None]
        assert finite == sorted(finite)
        assert thresholds[len(finite) :] == (None,) * (len(thresholds) - len(finite))
        assert all(1 <= threshold <= len(pages) for threshold in finite)
    expected = replay(trace, capacities, warmup_requests=warmup)
    assert optimized.curve(capacities) == expected
    assert unbounded.curve(capacities) == expected
    assert optimized.stats()["total_tokens"] == sum(item.input_tokens for item in trace[warmup:])
    assert optimized.stats()["accesses"] == sum(len(item.blocks) for item in trace)
    assert optimized.stats()["measured_requests"] == len(trace) - warmup
    assert optimized.stats()["requests"] == len(trace)


def test_lookup_must_precede_all_touches() -> None:
    trace = [request("a", "b"), request("b", "a")]
    profile = Profile(initial_slots=1)
    assert profile.observe(trace[0]) == (None, None)
    assert profile.observe(trace[1]) == (1, 2)
    # At capacity 1, b is present at entry even though the request is too big.
    # 容量为 1 时，虽无法容纳整个请求，进入时 b 仍可复用。
    assert profile.curve([1, 2]) == replay(trace, [1, 2])
    assert [row["reused_tokens"] for row in profile.curve([1, 2])] == [16, 32]
    profile = Profile()
    profile.observe(request("a", "b"))
    assert profile.observe(request("a", "b")) == (2, 2)
    assert profile.curve([1])[0]["reused_tokens"] == 0


def test_query_phase_precedes_touch_phase_during_compaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = Profile(initial_slots=4)
    profile.observe(request("a", "b"))
    profile.observe(request("b", "a"))
    events: list[tuple[str, str]] = []
    original_rank, original_touch = profile._index.rank, profile._index.touch

    def rank(block: str) -> int | None:
        events.append(("rank", block))
        return original_rank(block)

    def touch(block: str) -> None:
        events.append(("touch", block))
        original_touch(block)

    monkeypatch.setattr(profile._index, "rank", rank)
    monkeypatch.setattr(profile._index, "touch", touch)
    assert profile.observe(request("a", "b")) == (1, 2)
    assert events == [("rank", "a"), ("rank", "b"), ("touch", "a"), ("touch", "b")]
    assert profile.stats()["compactions"] == 1


def test_orphan_suffix_is_not_reusable() -> None:
    trace = [request("suffix"), request("new-prefix", "suffix")]
    profile = Profile()
    profile.observe(trace[0])
    assert profile.observe(trace[1]) == (None, None)
    assert profile.curve([0, 1, 2, 100]) == replay(trace, [0, 1, 2, 100])
    assert all(row["reused_tokens"] == 0 for row in profile.curve([0, 1, 2, 100]))


def test_cold_empty_tail_and_warmup() -> None:
    profile = Profile()
    assert profile.observe(request()) == ()
    assert profile.curve([0, 16])[0]["hit_rate"] == 0.0
    profile.observe(request("a", tail=15), measure=False)
    assert profile.observe(request("a", tail=15)) == (1,)
    assert profile.curve([1]) == [
        {"capacity_pages": 1, "reused_tokens": 16, "total_tokens": 31, "hit_rate": 16 / 31}
    ]
    assert profile.minimum_capacity(16 / 31) == 1
    assert profile.minimum_capacity(1) is None
    assert profile.minimum_capacity(0) == 0
    assert profile.stats()["accesses"] == 2
    assert profile.stats()["measured_requests"] == 2
    assert replay([request("a")], [1], warmup_requests=5)[0]["total_tokens"] == 0


def test_capacity_queries_do_not_mutate_profile() -> None:
    profile = Profile()
    for _ in range(2):
        profile.observe(request("a", "b", "c"))
    before = profile.stats()
    assert profile.curve([]) == []
    assert profile.curve([3, 0, 3, 2])[0] == profile.curve([3])[0]
    assert profile.minimum_capacity(0.5) == 3
    assert profile.minimum_capacity(0.50000001) is None
    assert profile.stats() == before
    empty = Profile()
    assert empty.minimum_capacity(0) == 0
    assert empty.minimum_capacity(0.01) is None


@pytest.mark.parametrize(
    ("blocks", "tokens", "block_size", "error"),
    [
        (["a"], 16, 16, TypeError),
        (("a", "a"), 32, 16, ValueError),
        (("",), 16, 16, ValueError),
        ((1,), 16, 16, ValueError),
        (("a",), 15, 16, ValueError),
        ((), -1, 16, ValueError),
        ((), True, 16, ValueError),
        ((), 1.0, 16, ValueError),
        ((), 0, True, ValueError),
        ((), 0, 0, ValueError),
        ((), 0, -1, ValueError),
        ((), 0, 1.0, ValueError),
        ((), 2**100, 16, ValueError),
    ],
)
def test_invalid_request(blocks: object, tokens: object, block_size: object, error: type) -> None:
    with pytest.raises(error):
        Request(blocks, tokens, block_size)


def test_request_is_immutable() -> None:
    item = request("a")
    with pytest.raises(FrozenInstanceError):
        item.input_tokens = 32


@pytest.mark.parametrize("invalid", [-1, True, 1.5, "4", None])
def test_invalid_capacities(invalid: object) -> None:
    profile = Profile()
    with pytest.raises(ValueError):
        profile.curve([invalid])
    with pytest.raises(ValueError):
        replay([], [invalid])


@pytest.mark.parametrize("invalid", [None, 2, "4", {1, 2}])
def test_invalid_capacity_container(invalid: object) -> None:
    with pytest.raises(TypeError):
        Profile().curve(invalid)


@pytest.mark.parametrize(
    "invalid", [-0.1, 1.1, 10**1000, float("nan"), float("inf"), True, "0.5", None]
)
def test_invalid_target(invalid: object) -> None:
    with pytest.raises(ValueError):
        Profile().minimum_capacity(invalid)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_unique_pages": 0},
        {"max_unique_pages": True},
        {"max_unique_pages": 1.5},
        {"initial_slots": 0},
        {"initial_slots": True},
        {"initial_slots": 1.5},
        {"compact": 1},
    ],
)
def test_invalid_profile_configuration(kwargs: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        Profile(**kwargs)


def test_resource_rejection_is_atomic_and_recovery_works() -> None:
    profile = Profile(max_unique_pages=2, initial_slots=1)
    profile.observe(request("a", "b"))
    state, curve = profile.stats(), profile.curve([0, 1, 2])
    with pytest.raises(ResourceLimitError):
        profile.observe(request("a", "c"))
    assert profile.stats() == state
    assert profile.curve([0, 1, 2]) == curve
    assert profile.observe(request("b", "a")) == (1, 2)
    fresh = Profile(max_unique_pages=1)
    with pytest.raises(ResourceLimitError):
        fresh.observe(request("a", "b", block_size=4))
    assert fresh.observe(request("a", block_size=8)) == (None,)


def test_multi_new_page_budget_rejection_preserves_internal_state() -> None:
    profile = Profile(max_unique_pages=3, initial_slots=2)
    profile.observe(request("a", "b"))
    before = (
        dict(profile._index.positions),
        profile._index.tree.tolist(),
        profile._index.clock,
        dict(profile._histogram),
        profile.stats(),
    )
    with pytest.raises(ResourceLimitError):
        profile.observe(request("c", "d"))
    after = (
        dict(profile._index.positions),
        profile._index.tree.tolist(),
        profile._index.clock,
        dict(profile._histogram),
        profile.stats(),
    )
    assert after == before
    assert profile.observe(request("b", "c")) == (1, None)
    assert profile.observe(request("b", "c")) == (2, 2)


def test_block_size_and_measure_rejection_are_atomic() -> None:
    profile = Profile()
    profile.observe(request("a"))
    before = profile.stats()
    with pytest.raises(ValueError):
        profile.observe(request("b", block_size=8))
    with pytest.raises(TypeError):
        profile.observe(request("a"), measure=1)
    with pytest.raises(TypeError):
        profile.observe("a")
    assert profile.stats() == before
    assert profile.observe(request("a")) == (1,)
    with pytest.raises(ValueError):
        replay([request("a"), request("b", block_size=8)], [1])
    with pytest.raises(TypeError):
        replay(["a"], [1])
    for warmup in (-1, True, 1.5):
        with pytest.raises(ValueError):
            replay([], [1], warmup_requests=warmup)


def test_reset_releases_state_and_allows_new_block_size() -> None:
    profile = Profile(initial_slots=2)
    for _ in range(10):
        profile.observe(request("a", "b", "c"))
    profile.clear()
    assert profile.stats() == {
        "unique_pages": 0,
        "allocated_slots": 2,
        "compactions": 0,
        "accesses": 0,
        "requests": 0,
        "measured_requests": 0,
        "total_tokens": 0,
    }
    assert profile.curve([100])[0]["reused_tokens"] == 0
    assert profile.observe(request("a", block_size=8)) == (None,)


def test_compaction_preserves_rank_and_bounds_storage() -> None:
    compact = Profile(initial_slots=4)
    unbounded = Profile(initial_slots=4, compact=False)
    for index in range(2_000):
        item = request(*(f"page-{(index + offset) % 8}" for offset in range(4)))
        assert compact.observe(item) == unbounded.observe(item)
        assert compact.stats()["allocated_slots"] <= max(4, 4 * compact.stats()["unique_pages"])
    assert compact.curve(list(range(12))) == unbounded.curve(list(range(12)))
    assert compact.stats()["compactions"] > 100
    assert unbounded.stats()["compactions"] == 0
    assert compact.stats()["allocated_slots"] * 100 < unbounded.stats()["allocated_slots"]


def test_rank_queries_are_pure_and_tree_occupancy_is_exact() -> None:
    rng = random.Random(9)
    index = RankIndex(compact=True, initial_slots=3)
    order: list[str] = []
    for _ in range(500):
        block = str(rng.randrange(15))
        before = (index.clock, index.compactions, index.slots, index.tree.tolist())
        assert index.rank(block) == (order.index(block) + 1 if block in order else None)
        assert before == (index.clock, index.compactions, index.slots, index.tree.tolist())
        if block in order:
            order.remove(block)
        order.insert(0, block)
        index.touch(block)
        assert sorted(index.positions) == sorted(order)
        assert all(index.rank(item) == rank for rank, item in enumerate(order, 1))


@pytest.mark.parametrize(
    ("unique", "compactions", "slots"), [(511, 1, 1024), (512, 1, 1024), (513, 0, 2048)]
)
def test_half_full_compaction_boundary(unique: int, compactions: int, slots: int) -> None:
    index = RankIndex(compact=True, initial_slots=1024)
    for page in range(unique):
        index.touch(str(page))
    for _ in range(1024 - unique):
        index.touch("0")
    before = [index.rank(str(page)) for page in range(unique)]
    index.touch("0")
    assert index.compactions == compactions
    assert index.slots == slots
    assert [index.rank(str(page)) for page in range(unique)] == before


def test_large_complete_request_and_unicode_namespaces() -> None:
    blocks = tuple(f"命名空间\u0000prefix/{index}" for index in range(10_000))
    item = Request(blocks, 10_000, block_size=1)
    profile = Profile(initial_slots=2)
    profile.observe(item, measure=False)
    assert profile.observe(item) == (10_000,) * 10_000
    assert profile.curve([0, 9_999, 10_000]) == replay(
        [item, item], [0, 9_999, 10_000], warmup_requests=1
    )
    assert profile.minimum_capacity(1.0) == 10_000
