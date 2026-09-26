# Security and limits

[简体中文](SECURITY_zh.md)

PrefixScope is an offline trace tool. It does not open a server, run model code or deserialize executable objects. JSON lines, page counts and distinct-page budgets are bounded. Hashing separates namespaces; it is not encryption or anonymization. A digest can still expose equality patterns.

Use only traces you may process. Do not publish proprietary token IDs or hashes. Keep downloaded traces and personal inputs outside Git. The Qwen benchmark uses already-public anonymized data and does not reconstruct prompts.

A configured budget violation is rejected before updating profiler state. An operating-system out-of-memory error is not transactionally recoverable: discard the instance and replay from a known checkpoint. The profiler has one owner; concurrent calls require external serialization. Arbitrary hostile inputs may still consume CPU within configured limits.

Do not use predicted cache hit ratios as latency guarantees, quality measurements or production capacity commitments. No live engine adapter, GPU, TTL, variable page size, pinning or concurrent scheduler is supported in this release.

For a report, share only a minimal non-sensitive reproducer through the repository's security reporting facilities if enabled. Avoid including secrets in public issues. No response-time or production-support commitment is offered.
