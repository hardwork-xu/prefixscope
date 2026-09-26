# Project descriptions and short talk

[简体中文](../zh/RESUME.md)

These statements describe the implemented artifact, not a claim that I have already mastered every topic. Before using them in an application, I should be able to reproduce the cited experiments and explain the assumptions. The work does not promise admission, employment or production impact.

## Four evidence-backed descriptions

1. Built a CPU prefix-cache capacity analyzer using request-entry LRU ranks and prefix-threshold histograms; on an Apple M1 Pro with Python 3.12.2, analyzing 64 capacities for the first 2048 requests of each public Qwen A/B trace took 761.55/437.09 ms median across five repeats, versus 4314.70/2347.14 ms for independent finite-LRU replay (5.67×/5.37×). This is trace-analysis speed, not inference speed.
2. Implemented order-preserving Fenwick timestamp compaction with an `O(U + S0)` rank-slot bound. On a labeled 20,000-request synthetic hot loop, allocated slots fell from 524,288 to 1,024; the real trace subsets showed no slot reduction. Process RSS is measured separately and is not claimed to fall by the same percentage.
3. Established exact correctness against an independent `OrderedDict` oracle with 100 random seeds and all capacities, plus tests for cold starts, partial tails, namespace isolation, budget rejection, compaction thresholds and reset/reuse; the core suite contains 153 passing cases.
4. Delivered reproducible raw evidence for 360 timed measurements across eight workloads, locked dependencies, bilingual API/CLI documentation, a wheel/source build, local acceptance records and GitHub Actions configuration. Executed versus unexecuted checks remain separately recorded.

## Evidence index

| Description | Implementation | Tests / configuration | Measurement |
|---|---|---|---|
| 1 | [profiler.py](../../src/prefixscope/profiler.py), [reference.py](../../src/prefixscope/reference.py) | [Frozen contract](../../experiments/contract.json) | [Raw repeats](../../results/benchmark.json), [generated summary](../../results/summary.json) |
| 2 | [rank.py](../../src/prefixscope/rank.py) | [Engine tests](../../tests/test_engine.py) | `hot_loop_20000`, `memory` and `stats` in raw results |
| 3 | [model.py](../../src/prefixscope/model.py), [trace.py](../../src/prefixscope/trace.py) | [Engine](../../tests/test_engine.py), [CLI/trace](../../tests/test_trace_cli.py) | [Acceptance logs](../../results/acceptance/checks.json) |
| 4 | [benchmark.py](../../benchmark.py), [CI](../../.github/workflows/ci.yml) | [Lock](../../requirements.lock), [benchmark tests](../../tests/test_benchmark.py) | [Release status](RELEASE.md) |

## A short explanation I can prepare

**Why this problem:** KVSET's September 2026 paper makes prefix working-set capacity a timely topic. Repeating the same request history for many budgets wastes work, but a credible implementation must define what a prefix hit means.

**How it works:** At request entry, each page has a stack rank. A prefix is resident only when every rank in it fits the capacity, so its threshold is the maximum rank. Aggregating those thresholds yields the curve. Timestamps track recency; compaction renumbers them without changing order.

**The main tradeoff:** This shifts work from one replay per capacity to rank maintenance shared by all capacities. It wins for many capacities but is substantially slower than a direct one-capacity replay. Compaction saves long-history index storage, with occasional rebuild pauses and no savings when most pages are new.

**The important experiment:** The two predetermined public trace subsets beat the 2× analysis target at 64 capacities with exact reused-token equality. The hot loop isolates memory compaction. All small-capacity regressions and repeated measurements remain visible.

**Failure cases:** An absent early page blocks later resident pages from being a usable prefix. A new namespace must not hit old identities. A budget overflow rejects the request before changing state. A real process OOM requires restarting the profile.

**Limits and next questions:** The model omits output KV, pinning and concurrency. Can an event adapter reproduce an engine's exact free-queue transitions? How should capacity analysis handle tenant pools or dynamic budgets? Can compaction pauses be reduced without hiding more state? These are future research questions, not completed features.
