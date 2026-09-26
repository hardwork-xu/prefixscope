# Attribution / 来源与归属

The project code is independently written and licensed under MIT. Mattson stack analysis, Fenwick trees, and prefix-capacity analysis are existing methods. No claim of a new cache principle, KVSET reproduction, or SOTA is made.

本项目代码为独立实现，采用 MIT 许可证。Mattson 栈分析、Fenwick 树和前缀容量分析均已有先例；不宣称新缓存原理、完整复现 KVSET 或 SOTA。

- Mattson et al., *Evaluation Techniques for Storage Hierarchies* (1970), [DOI](https://doi.org/10.1147/sj.92.0078).
- Fenwick, *A New Data Structure for Cumulative Frequency Tables* (1994), [DOI](https://doi.org/10.1002/spe.4380240306).
- Li et al., *The KV Cache Working Set: Online Capacity Planning for LLM Inference Systems*, [arXiv:2609.27746v1](https://arxiv.org/abs/2609.27746v1), submitted 23 September 2026. [Official implementation](https://github.com/llc-kc/kv_cache_capacity_estimator/tree/a90dc298151a8e117aa37e3c30fc0686de5225fa), inspected for algorithm and scope, not vendored.
- Alibaba Qwen-Bailian Anonymous Dataset, [fixed revision](https://github.com/alibaba-edu/qwen-bailian-usagetraces-anon/tree/5f7439c51ec248a0c585f7d90a41a6f57773b912). Apache-2.0; [original license](third_party/QWEN_DATA_LICENSE). Downloaded data stays outside Git. The benchmark uses the first 256 and 2048 records of traceA and traceB, discards partial input blocks, chains IDs by namespace and ignores output pages. These transformations do not recover original text. 原始公开数据不进入Git；取固定前缀子集，丢弃不足块，链接块身份，不纳入输出页，不能还原文本。
- Dataset reference: Wang et al., *KVCache Cache in the Wild: Characterizing and Optimizing KVCache Cache at a Large Cloud Provider*, USENIX ATC 2025, [paper page](https://www.usenix.org/conference/atc25/presentation/wang-jiahao).
- Citation File Format schema 1.2.0: [upstream schema](https://github.com/citation-file-format/citation-file-format/blob/1.2.0/schema.json), CC-BY-4.0; [original license](third_party/CFF_LICENSE). Copyright and attribution remain with the Citation File Format contributors. The schema is unchanged and vendored solely for offline metadata validation. 仅为离线引用元数据校验保留。

Runtime uses only the Python standard library. Development dependencies are listed and hash-locked in `requirements.lock`; their upstream licenses remain applicable. Python is PSF-licensed; pytest is MIT; Ruff is MIT; mypy is MIT; matplotlib uses its project license; setuptools is MIT; wheel is MIT; build is MIT; PyYAML is MIT; jsonschema is MIT. The wheel does not bundle those development packages.

运行时只使用Python标准库。开发依赖按哈希锁定，各自许可证继续有效；本项目wheel不捆绑开发依赖。
