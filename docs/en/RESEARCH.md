# Research

[简体中文](../zh/RESEARCH.md) · [Architecture](ARCHITECTURE.md) · [Source register](../../experiments/sources.json)

## Problem and topic selection

I chose capacity analysis because it connects a current inference problem to a question I can measure honestly on a CPU: how much time and analyzer memory are needed to evaluate many cache budgets? PrefixScope is an offline research and engineering tool for serving researchers and engineers inspecting prefix reuse. It does not execute a language model or allocate real KV tensors.

The selection window is **2026-09-21 through 2026-09-27**. These primary sources establish activity during that week, not a ranking of popularity or evidence of project originality.

| Candidate | Verified current work | Decision under the available resources |
|---|---|---|
| Prefix-cache capacity analysis | [KVSET, submitted September 23](https://arxiv.org/abs/2609.27746v1) | Selected: exact reference replay and public anonymized traces permit substantial CPU experiments. |
| Speculative decoding with less draft state | [H-Spec, submitted September 21](https://arxiv.org/abs/2609.24197v1) | Not selected: faithful evaluation requires trained draft/target models and suitable inference resources. |
| Recovery of low-bit reasoning quality | [On-Policy Distillation, submitted September 22](https://arxiv.org/abs/2609.26708v1) | Not selected: teacher/student training and reasoning evaluation exceed this local experiment's scope. |

The core question is: **can exact prefix-reuse curves avoid both a cache replay for every candidate capacity and rank storage proportional to the entire access history?**

## Prior work and contribution boundary

All-capacity LRU analysis follows [Mattson et al. (1970)](https://doi.org/10.1147/sj.92.0078). PrefixScope uses the cumulative-sum data structure described by [Fenwick (1994)](https://doi.org/10.1002/spe.4380240306). Neither the stack property, prefix maxima, nor logarithmic rank queries are claimed as new.

[KVSET](https://arxiv.org/abs/2609.27746v1) applies stack-distance analysis to KV-cache capacity planning. Its [pinned implementation](https://github.com/llc-kc/kv_cache_capacity_estimator/tree/a90dc298151a8e117aa37e3c30fc0686de5225fa) already supports consecutive-prefix metrics. This project is an independent, narrower implementation; it is not a reproduction of KVSET's production experiments or a new name for its method. No upstream implementation is bundled.

The concrete engineering contribution is an inspectable combination of:

1. Order-preserving compaction of a timestamp Fenwick index, so its structural storage follows distinct pages rather than total touches. Compaction can be disabled for an ablation.
2. A token-weighted threshold histogram, allowing capacities to be chosen **after** trace ingestion without retaining request history or updating every capacity on every access.
3. An explicit request-entry lookup contract, independent finite-cache reference implementation, strict inputs, bounded ingestion, and version-linked experiments on public traces.

These are engineering choices built from established techniques. Performance claims compare only the implementations and workloads actually measured. The request-entry contract improves auditability; it is not claimed to introduce a new prefix-hit algorithm.

## Model and definitions

The model is a serial sequence of completed requests. The benchmark uses full blocks of **B = 16 tokens**. The API permits other positive block sizes, but one profile must use a constant size. Each page ID includes its namespace and preceding prefix. IDs within a request are distinct.

For request `i`, let `n_i` be its complete input-token count and `p_i,1 ... p_i,m` its `m = floor(n_i / B)` full pages. An incomplete tail contributes to the denominator but never to reuse. Generated outputs are not inserted. Timestamps do not schedule overlapping execution.

Let `r_i,j` be a page's **1-based** position in the infinite LRU stack immediately before request `i`; an unseen page has rank infinity. All ranks are queried before any page is touched. Afterwards every page, including pages after the first miss, is touched left to right.

For a capacity of `C` pages, define:

```math
q_{i,j} = \max_{1 \le k \le j} r_{i,k}, \qquad
L_i(C) = \sum_{j=1}^{m_i} \mathbf{1}[q_{i,j} \le C].
```

`L_i` is the longest contiguous reusable prefix, not the number of independently resident pages. Once a cold page is encountered, every later threshold is infinite. For measured requests `M`:

```math
H(q)=B\sum_{i\in M}\sum_j\mathbf{1}[q_{i,j}=q],\qquad
R(C)=\sum_{q\le C}H(q),\qquad
h(C)=\frac{R(C)}{\sum_{i\in M}n_i}.
```

The implementation defines `h(C)=0` when the denominator is zero. Warmup requests change stack state but contribute neither histogram entries nor denominator tokens. A target above the maximum achievable rate returns `None`; zero target returns zero capacity. Page capacity can be converted to bytes only after supplying an appropriate constant bytes-per-page model externally; it is not a measurement of GPU memory.

## Why the result is exact within this model

**LRU invariant.** At every request boundary, a finite LRU of capacity `C` contains exactly the first `C` pages of the infinite stack, or the whole stack if smaller. Both implementations start empty and apply identical left-to-right touches, so the standard stack property preserves this invariant.

**Prefix threshold.** The first `j` pages are all resident at request entry exactly when every associated rank is at most `C`, equivalently `q_i,j <= C`. Summing these indicators counts the contiguous prefix. Consequently the histogram gives precisely the same integer reused-token count as independent finite replay.

**Compaction invariant.** Every known page owns one occupied timestamp. A Fenwick prefix sum counts occupied positions no later than that page; subtracting from the number of known pages gives its rank. When the timestamp array fills and at most half its slots are live, sorting the live timestamps and relabeling them `1 ... U` preserves their total order. It therefore preserves every rank and all future LRU behavior. Otherwise the array doubles without changing the occupied positions.

These arguments assume the supplied IDs represent interchangeable pages and ignore cryptographic collisions. They do not prove correspondence to a production serving engine.

## Complexity and resource costs

Let `A` be total full-page touches, `U` distinct pages, `K` queried capacities, `L` the largest request, and `S0` initial slots (default **1024**). These bounds use the usual word-RAM and expected dictionary-operation model; arbitrary native ID strings also require their actual byte storage.

| Component | Time | Additional state |
|---|---|---|
| Rank query / ordinary touch | `O(log(U + S0))` | Shared compact index |
| One compaction | `O(U log U + S)` sorting and rebuild | `O(U + S)` transient |
| Initialization and ingestion, amortized | `O(S0 + A log(U + S0))` | `O(U + S0 + L)` |
| Histogram and arbitrary-capacity curve | `O(U log U + K log K + U + K)` per curve call | `O(U + K)` transient |
| Independent finite LRU baseline | `O(K A)` expected | `O(sum_k min(C_k, U))` |

Compaction leaves at least half the array available for subsequent touches, amortizing its sorting and rebuilding cost. A doubling requires more than half the old slots to be live, giving `S <= max(S0, 4U)`; the unused index-zero element is additional. Histogram keys are ranks no greater than `U`. No request history is retained by `Profile`; `observe` temporarily returns up to `L` thresholds. With compaction disabled, the timestamp array is `O(A + S0)`. Python dictionaries, ID strings, loaded benchmark inputs and output objects are separate from the array-slot metric.

## Frozen hypotheses and acceptance

[contract.json](../../experiments/contract.json) predates performance tuning and is the authority for targets. They are not measured achievements.

| Kind | Predeclared statement |
|---|---|
| Target: speed | At least **2.0×** median analysis speedup over independent `OrderedDict` replay, separately on the first **2048** records of each Qwen trace A and B at **64** capacities. |
| Target: storage | Compact Fenwick allocated slots no more than **25%** of unbounded slots on `hot_loop_20000`; this is structural array storage, not process RSS. |
| Correctness | Exactly equal integer reused-token counts; **0** absolute error, with randomized differential testing across **100** seeds. |
| Expected, conditional | Increasing `K` should favor one-pass rank analysis; repeated hot pages should favor compaction. One-capacity and mostly-cold workloads may favor direct LRU. |

The grid is `64 + 256j` pages for `j=0...63`. Auxiliary cases use 256 or 2048 requests and 1, 8 or 64 capacities. The timing protocol uses one warmup execution, five repeats, shuffled implementation order, one thread and `perf_counter_ns`. It includes a fresh analyzer, ingestion of already-normalized requests and curve construction; input reading and normalization are excluded. Fresh-subprocess peak RSS includes input loading and is reported separately. These are analyzer measurements, not end-to-end model serving latency. Actual results belong in the experiment evidence, including regressions and failed targets.

## Data validity and external validity

The [Qwen-Bailian data](https://github.com/alibaba-edu/qwen-bailian-usagetraces-anon/tree/5f7439c51ec248a0c585f7d90a41a6f57773b912) is a public, anonymized production-derived trace, not a model or token-text corpus. Its Apache-2.0 terms and upstream attribution are retained separately. Selection uses the first `N` records in file order. Only complete input blocks are chained with a namespace; output lengths, arrival timing and incomplete block hashes do not create cache entries. The [upstream FAQ](https://github.com/alibaba-edu/qwen-bailian-usagetraces-anon/blob/5f7439c51ec248a0c585f7d90a41a6f57773b912/docs/qa-context-growth-pattern.md) explains tail padding changes. Synthetic stress traces are labeled separately.

The [pinned vLLM design](https://github.com/vllm-project/vllm/blob/379e9a1ea8a5995464d9bf775bcd36bb03a0995f/docs/design/prefix_caching.md) includes pinning, reference counts, output allocation and reverse-order release. PrefixScope models none of those mechanisms. It also excludes TTL, admission decisions, variable page sizes, tenant scheduling, multi-tier transfers and hybrid-attention state. Accurate production provisioning requires engine-specific validation beyond this release. A trace subset and an analyzer speedup cannot establish production throughput, TTFT improvement or GPU-memory savings.

Useful next research questions are how much engine eviction semantics change the curve, how output insertion affects estimated budgets, and whether approximate bounded-history analysis can retain useful error guarantees when `U` itself becomes too large.
