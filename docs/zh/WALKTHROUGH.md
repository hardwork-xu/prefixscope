# 维护者代码导读

[English](../en/WALKTHROUGH.md) · [架构与 API](ARCHITECTURE.md) · [研究说明](RESEARCH.md)

## 从入口开始

建议依次阅读 [`__main__.py`](../../src/prefixscope/__main__.py)、[`cli.py`](../../src/prefixscope/cli.py)、[`trace.py`](../../src/prefixscope/trace.py)、[`model.py`](../../src/prefixscope/model.py)、[`profiler.py`](../../src/prefixscope/profiler.py)、[`rank.py`](../../src/prefixscope/rank.py)，最后阅读 [`reference.py`](../../src/prefixscope/reference.py)。实现首次进入本地提交 `543f214`；后续修改以实际历史为准。

安装后，在仓库根目录执行：

```bash
.venv/bin/python -m prefixscope demo
.venv/bin/python -m prefixscope analyze examples/tokens.jsonl --format tokens --namespace walkthrough --capacities 0,4,8,64 --target 0.5
.venv/bin/python -m prefixscope analyze --help
```

`__main__.py` 以 `cli.main()` 的状态退出。安装后的 `prefixscope` 命令指向同一函数。`demo` 构造合成 token 请求、分析请求，并将完整曲线与独立回放对比，随后返回 JSON。`analyze` 读取本地 JSONL 流，逐请求调用 `observe`，输出曲线、计数器和目标命中率所需最小容量。状态 0 表示成功；已知输入、文件系统和算术错误产生双语诊断并返回状态 2。不可达目标输出 JSON `null`，并非错误。两种命令均不运行推理模型。

## 跟随输入进入请求模型

`load_jsonl` 以二进制方式打开文件，将单次读取限制为 `max_line_bytes + 1`，解码一个 JSON 对象，并产出一个不可变 `Request`。空行或格式错误会报告从 1 开始的行号。请求顺序保持不变。生成器在完成或显式关闭时关闭文件；提前停止迭代时应关闭生成器。

| 输入路径 | 机制 | 调试时检查 |
|---|---|---|
| `native` | 验证给定的 `blocks`、`input_tokens` 和可选 `block_size` | 标识已经是规范标识；namespace 参数不会重新散列这些标识。 |
| `tokens` | `from_tokens` 散列完整页；`chain_blocks` 纳入父前缀和命名空间 | 相同 token 页跟在不同前缀后，必须生成不同标识。 |
| `qwen` | 保留前 `floor(input_length / 16)` 个给定散列值，再进行链式散列 | 页大小为 16；不完整输入尾部保留在 token 分母中；不包含输出页。 |

`Request.__post_init__` 要求：`blocks` 是由唯一非空字符串组成的元组；`input_tokens` 是非负整数；`block_size` 是正整数；完整页数量恰为 `input_tokens // block_size`。布尔值不能作为整数参数。类型或形状错误抛出 `TypeError` 或 `ValueError`。模型无法证明调用方传入的 native 标识是否对应兼容的模型、分词器、适配器、精度和租户身份；分析前须确定这些边界。

## 跟踪一次状态转移

`Profile.observe(request, measure=True)` 分为四个阶段：

1. 验证参数、测量标志、固定页大小和加入新页后的不同页数。此阶段拒绝请求不改变状态。
2. 在任何 touch 之前读取**全部**页排名。未见过的标识排名为无穷，用 `None` 表示。每个位置取其前缀内排名的最大值；对测量请求，立即在该有限阈值的直方图项中累加 `block_size` 个 token。一旦出现冷页，其后阈值均为 `None`，不写入直方图。
3. 从左到右访问所有页，包括首次未命中之后的页。只有此阶段改变最近访问顺序。
4. 更新计数器，返回阈值元组。`measure=False` 仍返回阈值并更新最近访问顺序，但不计入直方图、测量请求数和 token 分母。

`curve(capacities)` 排序直方图阈值，以一次扫描处理排序后的容量，随后恢复调用方要求的顺序和重复项。每行包含 `capacity_pages`、精确整数 `reused_tokens`、精确整数 `total_tokens`，以及二者的浮点商 `hit_rate`。分母为零时返回 0.0。Profile 不保存请求历史。

`minimum_capacity(target_hit_rate)` 扫描同一有限阈值直方图。接受 `[0,1]` 内有限的 `int`/`float` 值，排除布尔值；非法值抛出 `ValueError`。目标为零返回 0，不可达的正目标返回 `None`。比较使用普通 Python 浮点表达式 `reused / total >= target`，**没有 epsilon 容差**。以 `32 / 70` 算得的目标能匹配同一报告值；其下一个更大的可表示浮点数可能要求更大容量。整数复用量仍然精确。

## 手算一个小反例

令 `a` 为规范首级页，`b`/`c` 为它的两个不同子页。页大小为 16；每个请求有 35 个 token，其中三个属于不完整尾页。先用 `(a,b)` 预热状态。

| 测量请求 | 进入时排名 | 前缀阈值 | 容量 2 的复用量 | 容量 3 的复用量 |
|---|---|---|---:|---:|
| `(a,c)` | `(2, infinity)` | `(2, infinity)` | 16 | 16 |
| `(a,b)` | `(2,3)` | `(2,3)` | 16 | 32 |

直方图为 `{2: 32, 3: 16}`，分母为 70。容量 2 复用 32 个 token，容量 3 复用 48 个。0.5 的目标需要 3 页容量；1.0 不可达。预热后，容量为 1 的缓存只保留 `b`，但再次请求 `(a,b)` 仍复用 **0** 个 token，因为首个页缺失，孤立后缀无法复用。独立累计各页命中会得到错误结果。

以下可执行检查复现该表和浮点边界：

```bash
.venv/bin/python - <<'PY'
import math
from prefixscope import Profile, Request, replay

trace = [Request(("a", "b"), 35), Request(("a", "c"), 35), Request(("a", "b"), 35)]
profile = Profile(initial_slots=4)
assert profile.observe(trace[0], measure=False) == (None, None)
assert profile.observe(trace[1]) == (2, None)
assert profile.observe(trace[2]) == (2, 3)
assert profile.curve([0, 1, 2, 3]) == replay(trace, [0, 1, 2, 3], warmup_requests=1)
assert [row["reused_tokens"] for row in profile.curve([2, 3])] == [32, 48]
assert profile.stats()["total_tokens"] == 70
assert profile.minimum_capacity(32 / 70) == 2
assert profile.minimum_capacity(math.nextafter(32 / 70, math.inf)) == 3
assert profile.minimum_capacity(0.5) == 3
assert profile.minimum_capacity(1.0) is None
profile.clear()
assert profile.stats()["unique_pages"] == 0
assert profile.observe(Request(("new",), 8, block_size=8)) == (None,)
print("walkthrough passed / 导读示例通过")
PY
```

## 检查排名索引及不变量

`RankIndex.positions` 将每个已知标识映射到唯一的占用时间戳。Fenwick 树保存占用计数。某页最近访问位置为 `p` 时，`rank` 返回 `U - prefix_sum(p) + 1`，其中 `U` 是已知页数量。最近访问的页排名为 1。查询不修改索引。

`touch` 先确保有可用槽位，删除已有旧占用点，增加时钟，再插入新占用点。数组耗尽时，如果 `U <= slots // 2`，`_make_room` 执行压缩：排序存活时间戳，重编号为 `1..U`，重建树；否则将数组容量翻倍。重编号保持访问顺序，因此保持全部排名。设置 `compact=False` 后，耗尽时始终扩展时间轴；这是内存消融，并不改变复用模型。

修改实现时检查以下不变量：

- 字典大小等于占用点数；同一标识不能拥有两个占用点。
- 有限阈值单调不减；`None` 后不再出现有限阈值。
- 直方图权重是 token 数，不能误当成页数；尾部只影响分母。
- 压缩改变位置，但保持排名。压缩模式的槽位数不超过 `max(initial_slots, 4 * U)`；`allocated_slots` 不含未使用的下标 0，也不代表进程 RSS。
- 所有排名查询先于访问更新。请求内标识唯一时，边查边更新所得的前缀最大值可能恰好相同；仅凭曲线相等不能证明阶段顺序正确。

`replay` 是正确性参考：每个容量使用独立的 `OrderedDict`，在请求进入时检查连续前缀，再从左到右访问并即时淘汰。它不调用排名索引或优化直方图。重构时应保留这种独立性。

## 调试、修改与扩展

先运行聚焦不变量的检查，再执行完整验证：

```bash
.venv/bin/python -m pytest tests/test_engine.py -q
.venv/bin/python -m pytest tests/test_engine.py -k 'query_phase or half_full or resource_rejection or orphan' -q
.venv/bin/python -m pytest tests/test_engine.py::test_randomized_against_independent_finite_lru --pdb -x
make test
make check
```

`test_query_phase_precedes_touch_phase_during_compaction` 包装真实方法，记录顺序的同时仍执行真实计算。`test_half_full_compaction_boundary` 覆盖 1,024 个槽位下的 511、512、513 个存活页。`test_randomized_against_independent_finite_lru` 将 100 个固定种子工作负载在全部测试容量下进行比较。`test_multi_new_page_budget_rejection_preserves_internal_state` 检查内部状态，而不仅是公开计数器。出现差异时，先借助这些测试定位，再查看基准时间。

`max_unique_pages` 限制标识数量，不限制字节数。超出预算时，在状态修改前抛出 `ResourceLimitError`；调整预算或输入后可以重试。系统 `MemoryError` **不保证事务回滚**：应丢弃该 Profile，并在新 Profile/进程中从已知输入重新开始。`clear()` 清空排名、直方图、计数器和已确定的页大小，允许改用另一页大小，但不保证 RSS 立即下降。`stats().requests` 和 `accesses` 包括预热。CLI 拒绝超过实际加载请求数的预热配置；库函数 `replay` 允许整个迭代输入都是预热，此时测量 token 数为零。

新增输入格式时，应转换为现有 `Request` 契约，并测试身份隔离、非法输入和尾部处理。替换排名数据结构时，应保留 `rank`/`touch` 行为及差分测试。不要静默扩展到并发、固定页、TTL、输出插入或不同页大小：这些条件改变缓存语义，可能破坏通用 LRU 栈。`Profile` 没有内部锁，只表示顺序完成的请求；外部串行化调用，也不等于模拟相互重叠的实际服务请求。

性能风险包括 Python 字典和字符串开销、直方图排序、压缩排序带来的停顿，以及大请求或命名空间的预处理成本。查询容量较少时，简单有限缓存基线可能更快。保留冻结的实验约定和不利结果，修改算法后重跑受影响实验。不能把元数据分析加速解释为推理加速。
