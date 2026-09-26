# Figure captions

**Capacity curves.** Public Qwen A/B subsets, first 2,048 records in original order; 64 capacities from 64 to 16,192 full 16-token pages. Every analysis begins with an empty cache and measures every request. Trace warmup is zero; the single discarded timing warmup is a separate full analysis. The token-weighted rate includes incomplete tail tokens in the denominator. Curves are finite-LRU reference values, exactly matched by both profiler variants. They describe the declared serial cache model, not measured inference latency.

**Memory.** The left panel reports allocated Fenwick slots on the synthetic 20,000-request hot loop, excluding unused index zero. The right panel reports measured process peak RSS in MiB for one fresh subprocess per workload/method with 64 capacities, including Python, input loading/normalization and the analyzer. Structural counts and RSS are different quantities. RSS has one sample per condition; no statistical memory-reduction claim follows.

Run ID: `c89dbb47-d85d-4866-9cdc-8b469be1c9aa`
