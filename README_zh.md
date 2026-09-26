# PrefixScope

[English](README.md)

我希望用一个可审计的 CPU 工具，研究前缀复用率怎样随缓存容量变化。实现沿用 Mattson 栈分析与 KVSET 的研究方向，工程贡献是可压缩的时间戳索引和明确的请求入口语义。本项目不执行模型推理，也不声称精确预测并发推理引擎。

实验前目标及测量协议已冻结于 [experiments/contract.json](experiments/contract.json)。
