# Development record

[简体中文](../zh/DEVELOPMENT.md)

This record describes work performed during the initial delivery on 27 September 2026 (Asia/Shanghai). It does not imply a longer development history, deployed customers or a published paper.

## Decisions and implementation

I selected prefix-capacity analysis after comparing this week's KVSET, H-Spec and low-bit distillation papers. The actual host has an Apple M1 Pro and 16 GiB RAM. A CPU trace analyzer permits meaningful correctness and resource experiments on that machine; a new large-model training pipeline would not have supported equivalent validation.

The initial directory contained no project files or Git repository. A separate repository was created without changing global Git identity. The numerical experiment contract was committed before the core implementation. The core was implemented from mathematical invariants rather than importing an upstream cache analyzer. The existing Mattson/Fenwick/KVSET ideas remain credited.

The implementation adds explicit request-entry queries, a histogram over prefix maxima, timestamp compaction, an independent `OrderedDict` replay, bounded ingestion, chain hashing and a bilingual CLI. Unit tests exercise both compressed and uncompressed paths and compare all capacities on 100 seeded random traces. The full benchmark then evaluates the predefined real trace subsets and unfavorable synthetic cases.

## Problems actually encountered

- The first hash-lock generation omitted setuptools because pip-tools classifies it as unsafe for automatic pinning. Regeneration with `--allow-unsafe` included a verified setuptools hash. This flag controls dependency inclusion; it does not disable package hash verification.
- Dependency metadata inspection found that then-current NumPy 2.5.3 and contourpy 1.4.0 require Python 3.12. NumPy 2.2.6 and contourpy 1.3.2 were explicitly pinned to preserve the declared Python 3.11 development path. Hash-locked installation was rerun.
- Strict typing found an `argparse.error` return annotation mismatch and an insufficiently narrowed JSON input value. The CLI now uses `NoReturn`; native input token counts are validated before constructing `Request`. Core assertions were retained.
- Source inspection and independent semantic review confirmed that cumulative maximum ranks may coincide under sequential touching when pages are unique. Therefore, a dedicated test checks actual read-before-write calls rather than incorrectly assuming aggregate hit counts can detect that implementation detail.
- License inspection corrected the vendored CFF schema attribution to CC-BY-4.0. Its original license is included. Qwen data remains Apache-2.0; downloaded source traces are excluded from Git.
- Docker, Podman and Colima are unavailable on the local host. The local container checks therefore remain `not_run`; any remote container result is recorded separately in the release evidence.

No performance target, capacity grid, real-data subset or valid measurement was changed after seeing the full results. Measured improvements belong to capacity analysis. Small-capacity regressions, no compaction benefit on the real subsets, and timing variation remain in the result files.

## Real commits

| Commit | Change | Validation at that stage |
|---|---|---|
| `72547f8` | Frozen scope, numeric targets and protocol | Environment and primary sources checked; no performance results yet |
| `543f214` | Core, finite-LRU oracle, input conversion, CLI | 178 core/interface tests; strict typing and lint passed |
| `9bcdd46` | Benchmark harness, raw evidence and analysis | 4 benchmark integration/schema/plot tests passed |
| `209e850` | Locked environment, build, CI, licenses and verification tools | Locked installation, lint and formatting passed |

These identifiers are actual local Git commits. Later documentation, evidence and publication changes are available in the repository history; the benchmark records its own exact revision and source digest.

```bash
git log --format='%h %s'
.venv/bin/python scripts/acceptance.py
```

[Acceptance checks](../../results/acceptance/checks.json) bind commands, actual exit statuses and sanitized logs to source versions. The raw benchmark was run while documentation/infrastructure changes were present, so its `working_tree_dirty` flag is true; its explicit hash covers all Python implementation files, the benchmark and the frozen contract. Release checks compare that digest with the final implementation.
