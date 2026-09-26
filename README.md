# PrefixScope

[简体中文](README_zh.md)

I am building an auditable CPU tool for studying how prefix reuse changes with cache capacity. The implementation follows Mattson stack analysis and KVSET's research direction; the project contributes a compacting timestamp index and explicit request-entry semantics. It does not run model inference or predict a concurrent serving engine exactly.

The pre-experiment targets and measurement protocol are frozen in [experiments/contract.json](experiments/contract.json).
