# Maintenance / 维护约定

- `src/prefixscope`: validated trace types, rank index, profiler, reference replay and CLI. `tests`: offline correctness; `experiments`: frozen contracts; `results`: measured evidence.
- 核心源码在 `src/prefixscope`；离线测试在 `tests`；实验前约定在 `experiments`；实测证据在 `results`。
- Install / 安装: `python3 -m venv .venv`; `.venv/bin/python -m pip install -r requirements.lock`; `.venv/bin/python -m pip install --no-build-isolation -e .`
- Verify / 验证: `make check`, `make test`, `make demo`, `make build`. Benchmark / 基准: `make benchmark`.
- Keep README and every `docs/en` / `docs/zh` pair semantically aligned. CLI help and public API descriptions must be bilingual. 中英文功能、数值和状态必须同步。
- Preserve all valid benchmark repetitions, failures, command/configuration, source hash and actual UTC time. Never turn targets into measured results. 保存所有有效样本、失败、命令、版本与真实时间，禁止伪造结果。
- Changes to semantics require differential tests against finite LRU and affected experiments rerun. 语义变更须进行独立 LRU 对照并重跑受影响实验。
- Do not publish private traces, credentials or machine paths; do not push, deploy, spend money, rewrite history or change global identity without task authorization. 未获当前任务授权，不公开私有数据，不推送、部署、付费、改写历史或修改全局身份。
- Done means implementation, tests, lint, typing, build, bilingual docs and version-linked evidence agree; unexecuted checks stay unverified. 完成意味着代码、测试、检查、构建、文档与版本证据一致，未执行项保留未验证状态。
