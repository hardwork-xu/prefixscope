# Release preparation

[简体中文](../zh/RELEASE.md)

Version: **0.1.0**. Package name and CLI: `prefixscope`. The source uses MIT; the public data and vendored CFF schema retain their separate licenses in [NOTICE](../../NOTICE.md). No DOI, paper acceptance, commercial deployment or package-index release is claimed.

## Reproduce locally

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

`dist/prefixscope-0.1.0-py3-none-any.whl` is the runtime package; `dist/prefixscope-0.1.0.tar.gz` contains source and reproduction material. The clean-install check creates a temporary virtual environment, verifies the full hash lock, installs the built wheel without dependencies from the local artifact, then executes API, demo and file-to-output analysis outside the source directory. The environment is removed afterward.

The default CPU demo needs no data download. `make fetch` uses curl and downloads about 153 MB of pinned public traces. For a fast offline CI-scale measurement:

```bash
.venv/bin/python benchmark.py --quick --output results/local-smoke.json
```

## Container path

```bash
docker build -t prefixscope:0.1.0 .
docker run --rm prefixscope:0.1.0 demo
docker run --rm -v "$PWD/examples:/data:ro" prefixscope:0.1.0 analyze /data/tokens.jsonl --format tokens
```

The image uses fixed Python 3.12.10 on Debian Bookworm, installs hash-locked packages, and runs as UID/GID 65534. It has no GPU path. The local host lacks Docker; **local container verification was not executed**. The ordinary Ubuntu GitHub Actions container job provides a separate opportunity for actual build/run verification. Configuration alone is not success evidence.

## Release-note draft

I am releasing a focused capacity-analysis tool built around explicit assumptions and reproducible evidence. Version 0.1.0 includes a compacting Fenwick rank index, prefix-threshold histogram, finite-LRU oracle, namespace-aware full-block ingestion, target-capacity queries and bilingual documentation.

On the recorded Apple M1 Pro run, the 64-capacity A/B 2048-request analyses were 5.67×/5.37× faster than independent finite-LRU replay, with exact reused-token equality. A 20,000-request synthetic hot loop reduced rank-index slots to 1/512 of the uncompressed variant. One-capacity replay remains faster; no inference acceleration or proportional RSS reduction is claimed.

## About and topics

English About: **Auditable prefix-cache capacity curves with compacting Fenwick ranks, exact LRU validation, and reproducible public-trace benchmarks.**

中文介绍：**可审计的前缀缓存容量曲线工具，结合可压缩 Fenwick 排名、精确 LRU 对照和可复现公开轨迹实验。**

Suggested Topics: `kv-cache`, `llm-inference`, `cache-analysis`, `lru`, `fenwick-tree`, `capacity-planning`, `benchmark`, `reproducible-research`, `python`, `bilingual`.

## Publication status

The initial package and source are prepared locally. Public GitHub synchronization is authorized for this delivery and is performed only after the local evidence and public-content scan are complete. The final repository/CI verification is recorded in `results/publication.json` when performed. PyPI upload, GitHub Release creation, DOI registration, container registry push and public service deployment are outside this delivery and have not been executed.

The GitHub Actions workflow tests Python 3.11 and 3.12 on Ubuntu 24.04 and builds/runs the CPU container. Each remote result must be read from the actual run. Local macOS success does not prove another platform passed.
