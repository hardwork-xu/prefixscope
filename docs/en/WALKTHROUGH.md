# Maintainer walkthrough

[简体中文](../zh/WALKTHROUGH.md) · [Architecture and API](ARCHITECTURE.md) · [Research](RESEARCH.md)

## Start at the entry point

Read these files in order: [`__main__.py`](../../src/prefixscope/__main__.py), [`cli.py`](../../src/prefixscope/cli.py), [`trace.py`](../../src/prefixscope/trace.py), [`model.py`](../../src/prefixscope/model.py), [`profiler.py`](../../src/prefixscope/profiler.py), [`rank.py`](../../src/prefixscope/rank.py), then [`reference.py`](../../src/prefixscope/reference.py). The implementation was introduced in local commit `543f214`; subsequent history records later changes.

Run these commands from the repository root after installation:

```bash
.venv/bin/python -m prefixscope demo
.venv/bin/python -m prefixscope analyze examples/tokens.jsonl --format tokens --namespace walkthrough --capacities 0,4,8,64 --target 0.5
.venv/bin/python -m prefixscope analyze --help
```

`__main__.py` exits with `cli.main()`'s status. The installed `prefixscope` command targets the same function. `demo` constructs synthetic token requests, profiles them, and compares the complete curve with independent replay before returning JSON. `analyze` reads a local JSONL stream, calls `observe` once per request, and emits the curve, counters and minimum target capacity. Status 0 means success; known input, filesystem and arithmetic errors produce a bilingual diagnostic and status 2. An unreachable target is JSON `null`, not an error. No inference model runs in either command.

## Follow ingestion into the request model

`load_jsonl` opens the file in binary mode, limits each read to `max_line_bytes + 1`, decodes one JSON object, and yields one immutable `Request`. Blank or malformed lines are errors with their 1-based line number. Request order is preserved. The generator closes its file on completion or explicit closure; close it when stopping iteration early.

| Input path | Mechanism | What to inspect when debugging |
|---|---|---|
| `native` | Validates supplied `blocks`, `input_tokens`, optional `block_size` | IDs are already canonical. The namespace argument does not rehash them. |
| `tokens` | `from_tokens` hashes each complete block; `chain_blocks` includes the parent and namespace | Identical token blocks following different prefixes must receive different IDs. |
| `qwen` | Keeps the first `floor(input_length / 16)` supplied hashes and chains them | The block size is 16; incomplete input tails remain in the token denominator; output pages are absent. |

`Request.__post_init__` requires a tuple of unique, nonempty string IDs; nonnegative integer `input_tokens`; positive integer `block_size`; and exactly `input_tokens // block_size` full pages. Booleans do not satisfy integer parameters. Type/shape violations raise `TypeError` or `ValueError`. The model cannot prove that caller-supplied native IDs represent compatible model, tokenizer, adapter, dtype and tenant identities. Establish those boundaries before profiling.

## Trace one state transition

`Profile.observe(request, measure=True)` has four phases:

1. Validate the argument, measurement flag, fixed page size and prospective number of distinct pages. Rejection here leaves state unchanged.
2. Read **all** page ranks before any touch. Missing IDs have rank infinity, represented by `None`. For each position, take the maximum rank seen in its prefix and, for measured requests, immediately add `block_size` tokens to the histogram at that finite threshold. Once a cold page appears, every later threshold is `None` and receives no histogram entry.
3. Touch every page from left to right, including pages after a miss. Only this phase changes recency.
4. Advance counters and return the tuple of thresholds. `measure=False` still returns thresholds and updates recency, but excludes the request from the histogram, measured-request counter and token denominator.

`curve(capacities)` sorts histogram thresholds and sweeps sorted capacities once, then restores the requested order and duplicates. Each row contains `capacity_pages`, exact integer `reused_tokens`, exact integer `total_tokens`, and their floating-point quotient `hit_rate`. A zero denominator gives 0.0. The profile retains no request history.

`minimum_capacity(target_hit_rate)` sweeps the same finite histogram. It accepts finite `int`/`float` values in `[0,1]`, excluding booleans; invalid values raise `ValueError`. Zero returns 0, and unattainable positive targets return `None`. The comparison is the ordinary Python floating-point expression `reused / total >= target`, with **no epsilon**. A target computed as `32 / 70` matches that same reported rate; its next larger representable float may need a larger capacity. Integer reuse accounting remains exact.

## Work a small counterexample by hand

Treat `a` as a first canonical page and `b`/`c` as its two alternative children. Page size is 16; each request has 35 tokens, including a three-token tail. First warm the state with `(a,b)`.

| Measured request | Entry ranks | Prefix thresholds | Reused at capacity 2 | Reused at capacity 3 |
|---|---|---|---:|---:|
| `(a,c)` | `(2, infinity)` | `(2, infinity)` | 16 | 16 |
| `(a,b)` | `(2,3)` | `(2,3)` | 16 | 32 |

The histogram is `{2: 32, 3: 16}` and the denominator is 70. Capacity 2 reuses 32 tokens; capacity 3 reuses 48. A 0.5 target needs 3 pages, while 1.0 is unattainable. Immediately after warmup, capacity 1 contains only `b`: repeating `(a,b)` still reuses **zero** tokens because the missing first page prevents reuse of the orphan suffix. Counting isolated page hits would give the wrong answer.

This executable check reproduces the table and the floating-point boundary:

```bash
.venv/bin/python - <<'PY'
import math
from prefixscope import Profile, Request, replay

trace = [Request(("a", "b"), 35), Request(("a", "c"), 35), Request(("a", "b"), 35)]
profile = Profile(initial_slots=4)
assert profile.observe(trace[0], measure=False) == (None, None)
assert profile.observe(trace[1]) == (2, None)
assert profile.observe(trace[2]) == (2, 3)
assert profile.curve([0, 1, 2, 3]) == replay(trace, [0, 1, 2, 3], warmup_requests=1)
assert [row["reused_tokens"] for row in profile.curve([2, 3])] == [32, 48]
assert profile.stats()["total_tokens"] == 70
assert profile.minimum_capacity(32 / 70) == 2
assert profile.minimum_capacity(math.nextafter(32 / 70, math.inf)) == 3
assert profile.minimum_capacity(0.5) == 3
assert profile.minimum_capacity(1.0) is None
profile.clear()
assert profile.stats()["unique_pages"] == 0
assert profile.observe(Request(("new",), 8, block_size=8)) == (None,)
print("walkthrough passed / 导读示例通过")
PY
```

## Inspect the rank index and its invariants

`RankIndex.positions` maps each known ID to exactly one occupied timestamp. A Fenwick tree stores the occupancy counts. For a page last touched at position `p`, `rank` returns `U - prefix_sum(p) + 1`, where `U` is the number of known pages. The most recent page has rank 1. A lookup never mutates the index.

`touch` makes room, removes the old occupied point if present, advances the clock, and inserts the new point. At array exhaustion, `_make_room` compacts when `U <= slots // 2`: it sorts live timestamps, relabels them `1..U`, and rebuilds the tree. Otherwise it doubles the array. Relabeling preserves recency order and therefore all ranks. With `compact=False`, exhaustion always grows the time axis; this is the memory ablation, not a different reuse model.

Inspect these invariants when changing the implementation:

- Dictionary cardinality equals the number of occupied points; no ID owns two points.
- Finite thresholds are nondecreasing, and no finite threshold follows `None`.
- Histogram weights are token counts, not page counts; tails affect only the denominator.
- Compaction changes positions but preserves ranks. Compact slots stay within `max(initial_slots, 4 * U)`; `allocated_slots` excludes the unused index-zero element and is not process RSS.
- All ranks are queried before touches. For unique IDs, sequential-touch prefix maxima can coincide numerically; curve equality alone does not prove this phase ordering.

`replay` is the correctness oracle: one independent `OrderedDict` per capacity, contiguous prefix membership at request entry, then left-to-right touches and immediate eviction. It does not call the rank index or optimized histogram. Keep that independence when refactoring.

## Debug, change and extend

Run focused invariants before the complete checks:

```bash
.venv/bin/python -m pytest tests/test_engine.py -q
.venv/bin/python -m pytest tests/test_engine.py -k 'query_phase or half_full or resource_rejection or orphan' -q
.venv/bin/python -m pytest tests/test_engine.py::test_randomized_against_independent_finite_lru --pdb -x
make test
make check
```

`test_query_phase_precedes_touch_phase_during_compaction` wraps actual methods to record ordering while executing their real calculations. `test_half_full_compaction_boundary` covers 511, 512 and 513 live pages at 1,024 slots. `test_randomized_against_independent_finite_lru` compares 100 seeded workloads across all tested capacities. `test_multi_new_page_budget_rejection_preserves_internal_state` checks more than public counters. Use these tests to isolate a disagreement before inspecting benchmark timings.

`max_unique_pages` bounds identities, not bytes. A budget violation raises `ResourceLimitError` before mutation; retry after choosing a suitable budget or input. System `MemoryError` is **not transactional**: discard the profile and restart from known input in a fresh profile/process. `clear()` resets ranks, histogram, counters and established page size; it permits a new page size but does not promise immediate RSS reduction. `stats().requests` and `accesses` include warmup. The CLI rejects warmup greater than the loaded request count; library `replay` permits an all-warmup iterable and returns zero measured tokens.

Add a format by converting it into the existing `Request` contract and testing identity separation, malformed input and tail handling. Replace the rank structure behind the same `rank`/`touch` behavior and differential tests. Do not silently extend this model to concurrency, page pinning, TTL, output insertion or variable page sizes: they change the cache semantics and may invalidate the universal LRU stack. `Profile` has no internal locking and represents serial completed requests; externally serializing calls does not model overlapping serving requests.

Performance risks include Python dictionary/string overhead, histogram sorting, compaction sorting pauses, and large request or namespace preprocessing. The simple finite-cache baseline can win for few capacities. Preserve the frozen experiment contract, keep unfavorable results, and rerun affected experiments after algorithm changes. Do not interpret faster metadata analysis as faster inference.
