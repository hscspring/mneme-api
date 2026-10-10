# mnemekit 0.8.2 Full Search 真实流量阶段报告

日期：2026-10-10  
来源：Agent Memory Leaderboard 文本赛道 Full 评测  
评测任务：`teval_9abcb4ed9849697f`  
核心版本：mnemekit 0.8.2，commit `fa03b70`  
API 版本：mneme-api 0.1.15，commit `d3f39f1`

## 1. 结论

mnemekit 0.8.2 已在原生产 Store 和 Full 真实请求上运行。API 没有修改 projection、Top-K、Evidence budget、tokenizer、Store、业务并发或返回格式，升级前后的 6 项 API 兼容测试全部通过，Store schema 保持为 3，无需迁移。

0.8.2 对真实流量有明确收益，但尚未解决 1,112-request Store 的主要性能瓶颈：

- 小 Store Search P50 从 0.8.1 的 10.99 秒降到 2.78 秒，降低约 74.7%。
- 1,112-request Store 的 `search_evidence()` P50 从 184.80 秒降到 174.16 秒，降低约 5.8%。
- 长历史 P95 从 404.01 秒降到 300.99 秒，降低约 25.5%。
- 长历史最大值从 489.02 秒降到 300.99 秒，降低约 38.5%。
- 10 条长历史样本仍全部需要 75.62–300.99 秒，离 P50 30 秒、P95 60 秒的目标很远。
- cgroup 峰值内存约 1.69 GiB，与 0.8.1 的 1.71 GiB 基本相同。
- 串行执行叠加平台 16 并发后，成功 HTTP 请求的端到端最大耗时已达到 1,659.36 秒，约 27.7 分钟，接近平台 30 分钟上限。

因此，0.8.2 修复的默认 `TAG_GRAPH_DEDUP` 重复 tokenize 问题确实存在且值得修复，但重复 tokenize 不是最大真实 Store 的唯一主瓶颈。下一步仍需直接对同一生产 Store 做阶段 profile，定位 activation、posting、候选集合、排序和 Evidence projection 中预算定位之外的成本。

本报告是首批 10 条长历史真实请求的阶段结论。Full 仍在运行，最终分布和 HTTP 超时数量应在 Search 阶段结束后补充。

## 2. 版本与不变量

0.8.2 的核心变化：

1. 修复默认 `TAG_GRAPH_DEDUP` 路径中的 O(n²) 重复 tokenize。
2. 将预算检查改为指数探测加二分定位。
3. 保持 Evidence 内容、顺序、分组、评分和完整越界 span 不变。

API 调用保持为：

```python
memory.search_evidence(
    query,
    topn=top_k,
    budget=EvidenceBudget(100_000, formatter.tokens),
)
```

部署配置：

| 项目 | 配置 |
| --- | --- |
| CPU | 2 vCPU |
| RAM | 约 1.9 GiB |
| Swap | 8 GiB |
| Uvicorn worker | 1 |
| API 业务并发 | 1 |
| 平台 Search 并发上限 | 16 |
| projection | 核心默认 `TAG_GRAPH_DEDUP` |
| Top-K | 100，在 Evidence projection 后执行 |
| Evidence budget | 100,000 `o200k_base` tokens，加完整边界 span |
| Store schema | 3，升级前后不变 |

0.8.2 服务于 2026-10-10 03:19:08 UTC 启动。平台保持原 Full 任务和检查点，没有新建任务或清空 Store。

## 3. 数据窗口

统计窗口：2026-10-10 03:19:08–03:51:24 UTC。

窗口内：

- 本地完成并写入 metrics 的 Search：13 条。
- 其中 `< 200` 历史请求 3 条，均为 161–163 requests。
- 1,112-request Store 10 条，而且是最近连续完成的 10 条。
- Full 平台进度：7,326 → 7,340，增加 14 条。
- Textual：5,773 → 5,783，增加 10 条。
- Streaming：1,553 → 1,557，增加 4 条。
- 返回最大值：609 spans、112,617 response tokens。

平台进度会延迟或批量提交，因此平台增量与本地 metrics 不要求逐秒对应。API 的 `search_ms` 从请求获得串行执行槽后开始计时，不包含信号量排队、HTTP response 发送和平台调度。

样本执行顺序显示，三个小 Store 请求之后连续出现十个 1,112-request Store 请求。结合 Textual 已完成 98.2%、Streaming 仅完成 39.0%，后续流量大概率已经进入长历史密集区，整体吞吐会低于评测前半段。

## 4. Search 延迟

### 4.1 按历史规模

| 历史请求数 | 样本数 | P50 | P95 | 最大 | 平均 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `< 200` | 3 | 2.78 s | 8.75 s | 8.75 s | 4.36 s |
| `200–999` | 0 | — | — | — | — |
| `1,112` | 10 | 174.35 s | 301.11 s | 301.11 s | 185.50 s |
| 全部 | 13 | 165.93 s | 248.68 s | 301.11 s | 143.70 s |

样本量仍小，尤其 P95 目前等于最大值，不能视为稳定总体估计。不过，10 条长历史全部超过 75 秒，已经足以证明当前问题不是单个异常 query。

### 4.2 1,112-request Store 分段耗时

| 阶段 | P50 | P95 | 最大 | 平均 |
| --- | ---: | ---: | ---: | ---: |
| Store 打开与恢复检查 | 0.239 s | 1.706 s | 1.706 s | 0.369 s |
| `search_evidence()` | 174.157 s | 300.987 s | 300.987 s | 185.130 s |
| API Evidence 格式化 | 0.004 s | 0.009 s | 0.009 s | 0.005 s |
| API 已计时总耗时 | 174.345 s | 301.105 s | 301.105 s | 185.504 s |

`search_evidence()` 占长历史总耗时超过 99.8%。Store 打开、恢复检查和 API 格式化都不是当前主瓶颈。

### 4.3 与 0.8.1 对比

| 1,112-request 指标 | 0.8.1 | 0.8.2 首批样本 | 变化 |
| --- | ---: | ---: | ---: |
| 样本数 | 17 | 10 | — |
| `search_evidence()` P50 | 184.80 s | 174.16 s | -5.8% |
| `search_evidence()` P95 | 404.01 s | 300.99 s | -25.5% |
| `search_evidence()` 最大值 | 489.02 s | 300.99 s | -38.5% |
| cgroup 峰值内存 | 1.71 GiB | 1.69 GiB | 基本不变 |

这不是严格的逐 query A/B：两个窗口中的 query 和服务器瞬时压力不同，且 0.8.2 样本较少。可以确认的是尾部暂时收窄，但长历史中位数只改善约 6%，与发布 microbenchmark 的 28.5 倍加速相差很大。

这说明 0.8.2 消除了一个放大项，但生产 Search 的绝大多数时间仍花在其他阶段。当前 API metrics 没有记录 budget callback 次数，无法仅凭线上日志验证真实请求的 tokenize 调用次数；核心方应在离线副本上增加 phase counter 做配对验证。

## 5. 内存与 HTTP 排队

0.8.2 服务启动后：

- cgroup `memory.peak` 为 1,813,491,712 bytes，约 1.69 GiB。
- 高位采样时 `MemoryCurrent` 约 1.63 GiB。
- 整机 `MemAvailable` 采样最低约 67 MiB。
- Swap 使用量从启动后的约 115 MiB 增长到约 567 MiB。
- 服务始终为 active，systemd `NRestarts=0`。

稳定运行窗口内，Caddy 已记录 13 个 Search HTTP 200：

| HTTP 200 端到端耗时 | 数值 |
| --- | ---: |
| 最短 | 1.70 s |
| P50 | 561.29 s |
| 最大 | 1,659.36 s |

服务启动后的稳定窗口暂未出现 30 分钟断开的 status 0。升级切换期间 03:18:30–03:19:14 UTC 曾出现集中 502；这些请求发生在服务停止或尚未 ready 的部署窗口，之后由平台重试，不能归因于 0.8.2 Search 行为。

目前业务并发为 1，平台可以同时发来 16 个 Search。单条核心耗时 2–5 分钟时，后续请求会在 API 信号量前排队。成功 HTTP 请求已经接近 30 分钟上限，即使单条核心 Search 自身没有超时，队列中的请求仍可能被平台断开。

## 6. 对 0.8.2 优化的判断

### 6.1 重复 tokenize 修复有效

小 Store P50 从约 11 秒降到 2.8 秒，长历史尾部从 489 秒暂时降到 301 秒，证明默认线上路径确实获得了收益。返回仍保持约 100K Evidence budget 加完整边界 span，API 格式化维持在毫秒级。

### 6.2 长历史主瓶颈仍在核心 Search

长历史 P50 只降低约 6%，并且 `search_evidence()` 仍占总耗时超过 99.8%。预算定位已经不再是唯一值得优化的部分。剩余候选包括：

- activation 的非 deictic channel 或完整可达状态构建。
- posting 块读取、解压和 ID 集合合并。
- candidate/tag 枚举以及 frontier 形成前的全量临时对象。
- unit/trace 预取和 payload 解码。
- 排序、去重、peak 选择和关系扩展。

### 6.3 内存没有实质改善

0.8.2 的 cgroup 峰值约 1.69 GiB，仍接近 0.8.1 的 1.71 GiB。2 GiB 主机无法安全增加 worker 或业务并发，Swap 增长也会放大尾延迟。减少 Python 对象工作集仍是 P0，而不只是部署容量问题。

## 7. 核心下一步建议

### P0：在真实 Store 副本上增加 phase profile

使用同一个 1,112-request Store 和固定 query 集，至少记录：

- 每个 activation channel 的时间、key 数和 candidate 数。
- posting 块读取数、解压字节数和合并后的 ID 数。
- unit/trace 读取数、payload 解码数和缓存命中。
- 排序、去重、peak 选择与 relation expansion 的时间和输入规模。
- Evidence projection 前后的 item/span/source 数。
- budget callback 次数、tokenize 总耗时和二分探测次数。
- 各阶段的 RSS 或 Python heap 增量。

至少选择一条约 75 秒、一条约 175 秒和一条约 301 秒的 query，做相同 query 的 0.8.1/0.8.2 或优化前后配对比较。

### P0：限制 frontier 形成前的对象物化

当前 Evidence budget 只限制 Reader 可见结果。如果 activation、posting、candidate 或排序在 40-source frontier 形成前仍创建与完整历史等比例的 Python 对象，时间和内存都不会随 100K budget 显著下降。

目标应是：完整规模只参与紧凑索引扫描，正文、unit、trace、span 和大型集合的物化规模主要受 frontier 和最终预算约束。

### P0：降低峰值内存

检查同一 source/posting ID 是否同时存在于多个 list、set 和 dict；检查解压 buffer、SQLite 行、payload 对象和排序输入是否跨 phase 同时存活。下一候选在同一 Store 上应把峰值压到 1.0 GiB 以下，才能为服务队列和操作系统保留余量。

### P0：支持 deadline 或取消

平台在 30 分钟后断开时，当前同步 Search 仍会继续执行并占用唯一串行槽。建议给 `search_evidence()` 增加可选 deadline/cancel token，在 activation、posting、批量读取和 projection 循环边界检查。

未提供 deadline 时保持现有行为；取消时不返回部分 Evidence，并应在 2 秒内释放大型临时对象。

### P1：把真实长历史作为发布门禁

保留 synthetic parity 和预算 callback microbenchmark，同时增加同一个 1,112-request Store 的固定 query 回归。每次发布至少报告 P50/P95、峰值 RSS、phase 分解、candidate/posting 数量和严格 Evidence parity。

## 8. 语义约束

后续优化必须继续保持：

- activation、排序、去重和 peak 语义不变。
- 无预算模式完整 Evidence 逐字段一致。
- 100K Reader 可见前缀逐 token、逐字段一致。
- 跨预算边界的完整 span。
- `source_id`、`role`、`timestamp`、`text` 不变。
- 默认 projection 和 Top-K 位置不变。
- schema 3 不做静默迁移。
- 不加入数据集、query、用户或 bad-case 特判。

## 9. 下一候选的真实门槛

| 指标 | 0.8.2 当前值 | 下一候选目标 |
| --- | ---: | ---: |
| `search_evidence()` P50 | 174.16 s | ≤ 30 s |
| `search_evidence()` P95 | 300.99 s | ≤ 60 s |
| 单条最大值 | 300.99 s | ≤ 120 s |
| 进程峰值 RSS | 1.69 GiB | ≤ 1.0 GiB |
| 取消响应 | 不支持 | ≤ 2 s |
| 稳定窗口 30 分钟断开 | 0，观察窗口尚短 | 0 |
| Evidence parity | 发布测试已保持 | 必须保持 |

下一版不应只以 tokenize microbenchmark 或 synthetic 总时延作为发布结论。需要证明真实 Store 的某个主要 phase 和峰值内存显著下降，并对固定 query 给出配对结果。

## 10. 当前运行决策

本轮 Full 继续运行 0.8.2：

- 不改变 projection、Top-K、100K budget、Store 或 API 返回格式。
- 持续收集真实长历史 latency、HTTP 状态、RSS、Swap 和平台进度。
- 当前服务仍健康，尚无理由重启。
- 若平台任务失败，仅从原任务断点续跑，不新建 Full。

第二次 Full 将于 2026-10-30 22:39 解锁。核心优化应先在生产 Store 副本上通过固定 query 门禁，再用于第二次 Full。
