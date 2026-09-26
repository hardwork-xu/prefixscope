# 发布准备

[English](../en/RELEASE.md)

版本：**0.1.0**；包名与 CLI 均为 `prefixscope`。源码采用 MIT，公开数据和随仓库提供的 CFF schema 保留[NOTICE](../../NOTICE.md)中的各自许可证。不宣称 DOI、论文录用、商业部署或已发布到包索引。

## 本地复现

```bash
make install
make demo
make check test
make fetch benchmark analyze
.venv/bin/python scripts/plot_capacity.py results/benchmark.json
make build
.venv/bin/python scripts/verify_install.py
.venv/bin/python scripts/acceptance.py
```

`dist/prefixscope-0.1.0-py3-none-any.whl` 是运行包；`dist/prefixscope-0.1.0.tar.gz` 包含源码与复现材料。干净安装检查建立临时虚拟环境，验证完整依赖哈希锁，再从本地构建产物无依赖安装 wheel，并在源码目录之外运行 API、示例和文件到输出分析，最后清理临时环境。

默认 CPU 示例不需要下载数据。`make fetch` 使用 curl 下载约 153 MB 固定版本的公开轨迹。快速离线 CI 规模测量：

```bash
.venv/bin/python benchmark.py --quick --output results/local-smoke.json
```

## 容器路径

```bash
docker build -t prefixscope:0.1.0 .
docker run --rm prefixscope:0.1.0 demo
docker run --rm -v "$PWD/examples:/data:ro" prefixscope:0.1.0 analyze /data/tokens.jsonl --format tokens
```

镜像固定 Python 3.12.10 / Debian Bookworm，按哈希锁安装依赖，以 UID/GID 65534 运行，没有 GPU 路径。本机缺少 Docker，**未执行本机容器验证**。普通 Ubuntu GitHub Actions 容器任务提供独立的实际构建/运行验证途径；配置存在不代表已经通过。

## 发布说明草稿

我将本工具定位为范围明确、假设透明、证据可复现的容量分析项目。0.1.0 包含可压缩 Fenwick 排名索引、前缀阈值直方图、有限 LRU 基线、带命名空间的完整块输入、目标容量查询与双语文档。

记录的 Apple M1 Pro 实验中，A/B 各 2048 请求、64 容量的分析相对独立有限 LRU 加速 5.67×/5.37×，复用词元数精确一致。20,000 请求合成热点循环的排名槽位为未压缩版本的 1/512。单容量回放仍更快；不宣称推理加速或 RSS 同比例下降。

## About 与 Topics

英文 About：**Auditable prefix-cache capacity curves with compacting Fenwick ranks, exact LRU validation, and reproducible public-trace benchmarks.**

中文介绍：**可审计的前缀缓存容量曲线工具，结合可压缩 Fenwick 排名、精确 LRU 对照和可复现公开轨迹实验。**

建议 Topics：`kv-cache`、`llm-inference`、`cache-analysis`、`lru`、`fenwick-tree`、`capacity-planning`、`benchmark`、`reproducible-research`、`python`、`bilingual`。

## 发布状态

初始包与源码已在本地准备。本次任务已授权公开 GitHub 同步，执行前先完成本地证据与公开内容扫描。实际执行后，最终仓库/CI 核验记录在 `results/publication.json`。本次交付不包含 PyPI 上传、GitHub Release 创建、DOI 注册、容器仓库推送或公网服务部署，以上均未执行。

GitHub Actions 在 Ubuntu 24.04 上测试 Python 3.11、3.12，并构建和运行 CPU 容器。远端结果必须读取实际 run；本机 macOS 成功不能证明另一平台已通过。
