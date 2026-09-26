# Contributing

[简体中文](CONTRIBUTING_zh.md)

I welcome small, reviewable changes that make the analysis easier to audit. Start with an issue describing the input, expected behavior and a minimal trace without private data.

1. Run `make install`, then `make check test demo build`.
2. Keep English and Chinese documentation aligned, including commands, limits and measured numbers.
3. For rank or cache semantics changes, compare every capacity against the independent finite-LRU oracle and add an adversarial example.
4. For performance changes, preserve the frozen experiment contract and every valid repetition. Record a new run with source hashes; never replace an unfavorable run to improve the headline.
5. Use Conventional Commits with an English subject and Chinese body. Include the checks actually run.

A passed synthetic benchmark does not establish a serving-engine speedup. Do not submit private prompts, tokens, customer traces, credentials or local machine paths. New backends must state exactly what was exercised.
