# mnemekit 0.8.0 Full Search 核心优化需求

日期：2026-10-10  
来源：Agent Memory Leaderboard 文本赛道 Full 评测  
评测任务：`teval_9abcb4ed9849697f`  
核心版本：mnemekit 0.8.0，Git tag `v0.8.0`，commit `9cd9e41`  
API 版本：mneme-api 0.1.13

## 1. 结论

mnemekit 0.8.0 已正确解决超大 Evidence 返回问题，但尚未解决长历史 Search 的核心计算成本。

0.8.0 在保持 Reader 可见前缀一致的前提下，将一个真实极端结果从 2,500 spans、约 503 万 tokens 收敛到约 50 spans、10 万 tokens。这项改动是正确且必要的，比赛 API 已按 100,000-token EvidenceBudget 接入。

然而，同一类真实大 Store 的有界 Search 仍出现：

- 单条耗时约 282 秒。
- 单进程峰值 RSS 约 1.57 GiB。
- 2 GiB 主机只能安全串行执行。
- 平台 Search 并发为 16，排队请求会在 30 分钟后断开。
- 客户端断开后，已经进入同步执行队列的 Search 仍会继续计算，占用执行槽和内存。
- Full 实际常见吞吐只有 1–3 条/5 分钟；按约 24 条/小时估算，剩余 2,575 条需要约 4.5 天。

因此，下一阶段不应继续调整 Evidence 返回格式，而应优化预算生效之前的 activation、candidate/posting 访问、对象解码和排序工作量，并让核心 Search 支持 deadline/cancellation。

本问题同时包含核心与 API 两层：API 的无界等待会放大拥塞，但单条 Search 本身已达到分钟级和 GiB 级峰值，只修改队列无法解决根因。

## 2. 0.8.0 已经解决的部分

0.8.0 的有界模式满足以下要求：

- EvidenceItem、EvidenceSpan 的排序和字段前缀保持不变。
- `source_id`、`role`、`timestamp`、`text` 保持不变。
- 保留跨预算边界的完整 span。
- 无预算模式与 0.7 完整 Evidence 语义一致。
- 有预算模式不再物化 Reader 永远不可见的 Evidence 尾部。
- schema 2 显式迁移到 schema 3，只读打开不静默改写 Store。

核心发布前的极端形态复现结果：

| 指标 | 无预算结果 | 100K 有界结果 |
| --- | ---: | ---: |
| EvidenceSpan | 2,500 | 50 |
| Evidence tokens | 5,039,038 | 100,788 |
| 前 100,000 个 `o200k_base` tokens | 一致 | 一致 |
| Evidence 字段与顺序前缀 | 一致 | 一致 |

这证明 EvidenceBudget 的语义设计成立。后续优化必须保留这项成果，不应通过减少召回、改变 projection 或重排 Evidence 来换取性能。

## 3. 真实 Full 的新增证据

### 3.1 单条真实大 Store Search

0.8.0 部署后，对真实最大 Store 的定向 Search 得到：

| 指标 | 结果 |
| --- | ---: |
| EvidenceItem | 1 |
| EvidenceSpan | 40 |
| Evidence tokens | 101,064 |
| 端到端耗时 | 282.398 秒 |
| 峰值 RSS | 1,574.3 MiB |

输出已经被正确限制在约 100K tokens，但耗时和峰值内存仍接近 0.6.0 的无界 Search。这说明主要成本发生在 Evidence 尾部物化之前。

### 3.2 Full 在线表现

部署环境：

| 项目 | 配置 |
| --- | --- |
| CPU | 2 vCPU |
| 内存 | 约 1.9 GiB |
| Swap | 8 GiB |
| Uvicorn worker | 1 |
| API 内部业务并发 | 1，Add/Search 共用串行信号量 |
| 平台并发上限 | Add 16、Search 16 |
| Search | `search_evidence(query, topn=top_k, budget=100K)` |

典型运行周期如下：

1. 服务重启后 RSS 约 260–300 MiB，可用内存约 1.4–1.5 GiB。
2. 平台很快建立多个并发 Search。
3. 当前请求执行时，RSS 可升到 1.5–1.7 GiB，可用内存降到 60–100 MiB。
4. 单条重 Search 完成后，RSS 可回落到 0.8–1.2 GiB。
5. 后续排队请求已接近或超过平台 30 分钟连接上限。
6. Caddy 记录 `/search` 以 `status=0`、`duration≈1800s` 结束，但后台同步计算仍可能继续。
7. 多轮累积后，Health 和 SSH 延迟上升，需要人工重启服务清理失效队列。

最近一次干净重启后的连续观测中，平台进度从 7,300 增至 7,311，约 25 分钟完成 11 条，折合约 26 条/小时。其他窗口常见 1–3 条/5 分钟。

平台进度存在延迟和批量更新：曾在长时间不变后一次增加 48。因此，平台计数不能单独用于判断某条请求是否成功；需要同时结合 HTTP 200、服务端指标和任务状态。这个现象不改变核心吞吐结论。

### 3.3 返回规模已不再是主瓶颈

当前成功 Search 通常返回约 100K–102K tokens 和约 40–53 spans。API 格式化和网络体积已经比 0.6.0 的 500 万 token 结果小两个数量级，但单条核心 Search 仍可持续数分钟。

因此，下一轮 profile 应集中在：

- activation 图遍历。
- candidate key/tag 枚举。
- posting 块读取与解压。
- unit/trace 读取和反序列化。
- 排序、去重和 peak 选择。
- EvidenceBudget 决策之前已经创建的 Python 对象。

## 4. 核心与 API 的责任边界

### 4.1 核心必须解决

- 单条 Search 的分钟级延迟。
- 单条 Search 的 1.5 GiB 级峰值 RSS。
- 预算已经达到后仍发生的大量候选访问或对象创建。
- 无法响应 deadline/cancellation，导致客户端断开后继续占用计算资源。
- 在真实高频 tag、大 posting、高连通 activation 图上的工作量失控。

### 4.2 API 必须解决

- 限制等待队列长度，避免平台 16 并发无限堆积。
- 将客户端断开、服务端 deadline 传递给核心。
- 对尚未开始的过期请求停止排队。
- 在核心内存下降后再开放有限并行。
- 继续负责精确的 `o200k_base` Reader token budget。

API 无法安全取消一个已经进入纯同步核心调用、且核心不检查取消状态的 Search。仅返回 503 也不能提高单请求性能，并可能增加平台重试压力。

### 4.3 平台特性

- 单个 Add/Search 请求最长等待 30 分钟。
- 平台会对临时错误做有界重试。
- 任务失败后可从原任务断点续跑，不新增 Full 次数。
- 平台进度可能延迟或批量提交，不应把短期计数不变直接解释为结果丢失。

## 5. P0 核心需求

### 5.1 给预算之前的工作量设上限

EvidenceBudget 不能只限制最终 span 物化，还需要尽可能限制上游工作量。对最终无法进入预算前缀的候选，不应读取正文、构造完整 unit/trace 对象或创建 EvidenceSpan。

可选实现由核心模块决定，但需要满足以下性质：

- 使用紧凑元数据先确定可能进入 Top-K/预算前缀的 source。
- posting 以迭代器或块方式消费，不把全部 posting 展开成 Python 对象。
- 排序尽量使用有界 heap、增量归并或等价结构。
- unit/trace 正文只为最终保留 source 批量读取。
- 达到可证明的预算边界后停止后续正文物化。

如果精确 Evidence 顺序要求检查全部 posting，可以保留紧凑扫描，但仍应避免加载全部正文和构造完整对象图。

### 5.2 支持 deadline 和 cancellation

建议核心公开可选的 deadline/cancellation 参数，或等价的轻量检查机制。它应在 activation、posting 块遍历、批量读取和 Evidence projection 的循环边界检查。

要求：

- 未传参数时保持现有行为。
- 取消后不提交 Store 变更；Search 本身应为只读。
- 从触发取消到返回/抛出专用异常的时间不超过 2 秒。
- 不吞掉取消，不把部分 Evidence 当成功响应返回。
- API 能把客户端断开或内部 deadline 映射到该机制。

这项能力是清除失效请求的必要条件。即使单条 Search 尚未完全优化，也能避免一个已断开的请求继续阻塞几十分钟。

### 5.3 控制峰值工作集

Search 的峰值内存应主要与 Reader 预算和有界候选集合相关，而不是与整个用户历史或完整 posting 正文线性增长。

重点检查：

- SQLite 行解码后是否同时保留压缩数据和解压对象。
- posting、unit、trace 是否存在重复容器或多份 ID 集合。
- phase 间的大列表是否能及时释放。
- cache 是否在单请求中无界增长。
- 多个相同 source 是否被重复读取或重复构造。

## 6. P1 优化方向

### 6.1 分阶段 profile

在改变算法前，先对 untouched 的真实 schema 3 Store 副本增加阶段计时和峰值采样：

- Store 打开。
- activation。
- candidate 枚举。
- posting 读取/解压。
- unit/trace 预取。
- 排序与去重。
- budget 判定。
- span 物化。
- 总耗时与峰值 RSS。

profile 只需进入离线 benchmark，不要求污染公共 API 或生产结果。

### 6.2 复用只读结构

如果 profile 证明每次 Search 都重复解码相同的不可变索引，可以考虑 Store 级只读页缓存或紧凑 mmap/SQLite page reuse。缓存必须有明确上限，不能再次把完整用户历史长期驻留在 Python 对象中。

### 6.3 面向并行的内存目标

当前 2 GiB 主机无法运行两个 1.5 GiB Search。核心单请求工作集下降后，API 才能安全把执行并发从 1 提升到 2–4。并行不是第一步；先降低单请求成本，再测有限并行下的吞吐与尾延迟。

## 7. 必须保持的语义

性能优化不得改变：

- 默认 projection 和 activation 语义。
- EvidenceItem 排序。
- item 内 EvidenceSpan 排序。
- 去重规则和 peak 选择规则。
- `source_id`、`role`、`timestamp`、`text`。
- 预算前缀及跨边界完整 span。
- 相同 Store/query/topn/budget 的确定性。
- 无预算模式与 0.8.0 完整 Evidence 的逐字段一致性。
- schema 3 Store 的读写和显式迁移语义。

不得通过数据集名称、query 文本、用户 ID、固定 bad case 或比赛专用规则规避重 Search。

## 8. 离线复现与验收方法

### 8.1 两套基准

1. **真实 Store 门禁**：使用生产 Store 的离线副本，不提交原始文本、用户 ID 或评测数据到仓库。
2. **可公开 synthetic 基准**：构造高频 tag、2,500 sources、大 posting 和高连通 activation 图，复现相同计算形态。

每个 benchmark 都应记录机器、CPU、内存、Python、mnemekit commit、Store schema 和数据库大小。

### 8.2 对照组

- 0.8.0 无预算完整结果。
- 0.8.0 100K 有界结果。
- 新候选的无预算结果。
- 新候选的 100K 有界结果。

先验证逐字段和 token 前缀 parity，再比较性能。真实 Store 应从 untouched 副本冷开，避免缓存或迁移状态污染结果。

### 8.3 必测场景

- 冷开后的第一次 Search。
- 相同 Store 的重复 Search。
- 高频 tag 命中大部分 source。
- 多个中等 item 共同填满 budget。
- 第一个 item 自身超过 budget。
- deadline 在 activation、posting 和 projection 阶段触发。
- 客户端取消后立即执行下一条正常 Search。
- 连续 100 条 Search 后检查 RSS 是否回到稳定区间。

## 9. 发布门槛

在 2 vCPU、2 GiB RAM、单 worker 环境，以当前真实极端 Store 为硬门：

| 指标 | 门槛 |
| --- | ---: |
| 100K Reader 可见前缀 | 与 0.8.0 逐 token、逐字段一致 |
| 无预算 Evidence | 与 0.8.0 逐字段一致 |
| 典型 Search P50 | ≤ 5 秒 |
| 典型 Search P95 | ≤ 15 秒 |
| 当前极端 Store单条 Search | ≤ 30 秒 |
| 单进程 Search 峰值 RSS | ≤ 1.0 GiB |
| 取消响应时间 | ≤ 2 秒 |
| 连续 100 条 Search 的 RSS 漂移 | ≤ 10% |
| 超过平台 30 分钟上限 | 0 条 |

如果第一版无法一次达到最终延迟门槛，至少应先通过以下恢复 Full 的最低门槛：极端 Store ≤ 120 秒、峰值 RSS ≤ 1.2 GiB、取消 ≤ 2 秒，并给出到最终门槛的 profile 证据。仅改善 synthetic、但真实 Store 仍为分钟级，不应发布为性能问题已解决。

## 10. 交付物

核心实现方交付下一候选时，请同时提供：

1. 核心 commit 和待发布版本号。
2. 真实 Store 各 phase 时间、峰值 RSS 和总耗时。
3. 0.8.0 与候选版本的 Evidence parity 结果。
4. deadline/cancellation 的行为测试。
5. synthetic benchmark 脚本与结果。
6. schema 兼容与迁移说明。
7. API 接入所需的最小调用示例。

候选先在离线真实 Store 上通过门禁，再发布 PyPI。生产 Full 不应直接承担性能试错。

## 11. API 侧后续动作

核心候选通过后，API 侧将：

1. 接入 deadline/cancellation，并停止执行已断开请求。
2. 将等待队列限制为明确的小容量，不让 16 个请求全部进入同步线程池。
3. 保持 `top_k`、projection 和 100K EvidenceBudget 不变。
4. 在同一真实 Store 复测端到端延迟、HTTP 200、RSS 和 Caddy 断开数。
5. 根据单请求峰值决定是否把业务并发从 1 提升到 2–4。
6. 重新执行 Smoke 后，再决定下一次 Full 的部署资源和并发。

本轮 Full 继续使用冻结的 mnemekit 0.8.0 获取基准分，不在运行中替换核心算法或 Evidence 语义。
