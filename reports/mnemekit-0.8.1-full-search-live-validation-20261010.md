# mnemekit 0.8.1 Full Search 真实流量验证

日期：2026-10-10  
来源：Agent Memory Leaderboard 文本赛道 Full 评测  
评测任务：`teval_9abcb4ed9849697f`  
核心版本：mnemekit 0.8.1  
API 版本：mneme-api 0.1.14，commit `2793008`

## 1. 结论

mnemekit 0.8.1 已在生产 Store 和真实 Full 请求上生效，Evidence 语义、100K Reader budget 和 schema 均保持兼容。升级后无需迁移，API 本地与远端测试均为 6/6 通过。

本次两项优化有效，但收益集中在小 Store 和长历史 Search 的中位延迟：

- 历史请求少于 200 的 Search P50 为 10.99 秒，P95 为 13.45 秒。
- 1,112-request Store 的 Search P50 为 184.80 秒。
- 0.8.0 对同类最大 Store 的定向 Search 为 282.40 秒，0.8.1 长历史中位数降低约 35%。
- 1,112-request Store 的 P95 仍为 404.01 秒，最大为 489.02 秒。
- 服务进程峰值内存约 1.71 GiB，与 2 GiB 主机的容量仍不匹配。
- 部署后窗口内 Caddy 记录 15 个 Search HTTP 200 和 23 个等待约 30 分钟后断开的 Search。

因此，0.8.1 是明确进步，但没有消除长历史主瓶颈。预算函数的指数探测和 deictic frontier 优化没有覆盖当前最重 Store 的主要工作量。下一步应直接 profile 1,112-request Store 的 `search_evidence()` 内部阶段，优先寻找 activation、非 deictic candidate、posting 解码或大规模临时对象中的剩余热点。

当前版本可以继续运行以取得基准分，但不应把这组结果视为性能问题已经解决。

## 2. 版本与部署

0.8.1 包含两项保持 Evidence 等价的性能优化：

1. 只物化既有 40-source frontier 所需的 deictic activation。
2. EvidenceBudget 从逐条重复测量改为指数探测和二分定位；tokenizer 仍由 API 提供。

API 保持以下调用不变：

```python
memory.search_evidence(
    query,
    topn=top_k,
    budget=EvidenceBudget(100_000, formatter.tokens),
)
```

生产部署没有修改 projection、Top-K、tokenizer、Store、用户数据或 API 并发：

| 项目 | 配置 |
| --- | --- |
| CPU | 2 vCPU |
| RAM | 约 1.9 GiB |
| Swap | 8 GiB |
| Uvicorn worker | 1 |
| API 业务并发 | 1 |
| 平台 Search 并发上限 | 16 |
| projection | 核心默认值 |
| Evidence budget | 100,000 `o200k_base` tokens，加完整边界 span |
| Store schema | 3，升级前后不变 |

服务于 2026-10-10 01:46:27 UTC 左右启动，新进程 PID 为 `126053`。Full 从原任务检查点恢复为第 12 次尝试，没有新建 Full。

## 3. 数据窗口

统计窗口：2026-10-10 01:47:39–02:53:23 UTC。

窗口内：

- 本地完成并写入 metrics 的 Search：22 条。
- Full 平台进度：7,312 → 7,326，增加 14 条。
- Textual：5,763 → 5,773。
- Streaming：1,549 → 1,553。
- 返回最大值：659 spans、102,283 evidence tokens。

平台进度存在延迟和批量提交，因此平台增加 14 与本地完成 22 不要求一一同时出现。核心延迟使用 API 在获得串行执行槽后记录的 `search_ms`，不包含信号量排队时间、HTTP response 发送和平台调度延迟。

## 4. Search 延迟

### 4.1 按历史规模

| 历史请求数 | 样本数 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: |
| `< 200` | 5 | 10.99 s | 13.45 s | 13.89 s |
| `200–999` | 0 | — | — | — |
| `≥ 1000` | 17 | 184.80 s | 404.01 s | 489.02 s |
| 全部 | 22 | 161.17 s | 378.85 s | 489.02 s |

所有 `≥ 1000` 样本都来自同一个 1,112-request Store。该组结果表明 0.8.1 对长历史中位数有帮助，但尾延迟仍会达到 6.7–8.2 分钟。

### 4.2 1,112-request Store 分段耗时

| 阶段 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: |
| Store 打开与恢复检查 | 0.142 s | 0.561 s | 0.592 s |
| `search_evidence()` | 184.800 s | 404.007 s | 489.016 s |
| API Evidence 格式化 | 0.007 s | 0.014 s | 0.016 s |
| API 已计时总耗时 | 184.976 s | 404.573 s | 489.615 s |

P50 中 `search_evidence()` 占已计时总耗时超过 99.9%。Store 打开和 API 格式化均不是当前问题。

### 4.3 与 0.8.0 对比

0.8.0 对最大真实 Store 的定向 Search：

- 1 item。
- 40 spans。
- 101,064 evidence tokens。
- 282.398 秒。
- 峰值 RSS 1,574.3 MiB。

0.8.1 的第一条 1,112-request Search 为 131.41 秒，完整窗口的 17 条长历史样本 P50 为 184.80 秒。以 0.8.0 的 282.40 秒定向结果作参考，0.8.1 长历史中位数约快 1.53 倍；但两者不是严格配对 query，不能当作逐 query A/B。

更重要的是，0.8.1 长历史 P95 和最大值仍高于该 0.8.0 单条参考值，说明剩余热点会随 query 命中形态或运行期资源压力显著变化。

## 5. 内存与 HTTP 行为

0.8.1 服务启动后：

- 空闲期 MemoryCurrent 约 190–260 MiB。
- 观测窗口末 MemoryCurrent 约 1.58 GiB。
- systemd/cgroup 记录的 MemoryPeak 为 1,831,682,048 bytes，约 1.71 GiB。
- 采样时整机可用内存约 438 MiB。
- Swap 已用约 1.05 GiB。

在同一窗口的 Caddy Search 记录中：

| HTTP 结果 | 数量 |
| --- | ---: |
| 200 | 15 |
| status 0，连接断开 | 23 |
| 405 | 1 |

HTTP 200 的端到端持续时间最短约 9.92 秒，最长约 1,720.37 秒。status 0 请求通常持续约 1,800 秒，对应平台单请求 30 分钟等待上限。

本地 metrics 记录 Search 核心完成，不代表原 HTTP 客户端仍连接。平台断开后，当前同步调用不能取消，后台 Search 会继续占用串行执行槽。这是 API 排队放大问题，但其触发条件仍是核心长历史 Search 过慢。

## 6. 对 0.8.1 两项优化的判断

### 6.1 EvidenceBudget 指数探测有效

0.8.1 发布验证显示，2,500 spans、99,500 tokens 的预算定位只调用预算函数 13 次。真实 Full 中 API 格式化仅需毫秒级，返回仍稳定在约 100K–102K tokens，说明预算边界实现正确。

这项优化消除了重复 tokenize/format 的潜在放大，但真实 1,112-request Store 的 `search_evidence()` 仍需数分钟，证明预算测量已经不是主耗时。

### 6.2 Deictic frontier 优化有效但覆盖有限

发布 microbenchmark 中 deictic 场景中位耗时从约 70 ms 降到 7.6 ms，约快 9.2 倍。真实 Full 的小 Store 也能稳定在约 11 秒。

长历史组仍为 185–489 秒，说明极端 Store 的主要成本不只来自已优化的 deictic activation 物化。需要用 phase profile 判断剩余成本属于：

- activation 的其他 channel 或非 deictic 状态。
- candidate/tag 枚举。
- posting 块读取与解压。
- unit/trace 批量读取和对象解码。
- 排序、去重和 peak 选择。
- 进入 40-source frontier 之前创建的临时集合或对象。

## 7. 核心下一步建议

### P0：对 1,112-request Store 做 phase profile

不要继续从 synthetic microbenchmark 推断主瓶颈。直接使用 untouched 的生产 Store 离线副本，对同一批真实 query 记录：

- activation 各 channel 的时间和候选数。
- posting 读取块数、条数、解压字节数。
- unit/trace 读取数量和缓存命中。
- 排序、去重、peak 选择。
- EvidenceBudget 探测次数及其累计时间。
- 各阶段前后的 RSS 和 Python 对象数量。

至少区分一条约 130 秒样本和一条超过 400 秒样本，找出尾延迟随 query 变化的来源。

### P0：让候选工作集也受 frontier 约束

0.8.1 已限制 deictic activation 的物化，但如果其他 channel、posting 或排序仍在 frontier 形成前全量展开，峰值仍会随 Store 历史增长。

目标应是：只让紧凑索引扫描与完整候选规模相关，正文读取和 Python 对象数量主要与最终 frontier/Reader budget 相关。

### P0：降低单 Search 峰值 RSS

当前约 1.71 GiB 的进程峰值使 2 GiB 主机无法并行，也会引发 Swap 抖动和尾延迟放大。重点检查：

- 同一 posting/source ID 是否存在多份 list/set/dict。
- 解压 buffer 和解码对象是否同时存活。
- phase 结束后临时对象是否仍被引用。
- unit、trace 和 span 是否在预算筛选前批量创建。
- SQLite 批量读取是否返回远超 frontier 所需的完整行。

### P0：增加可取消 Search

平台在 30 分钟后断开时，核心仍继续运行。建议给 `search_evidence()` 增加可选 deadline/cancel token，并在 activation、posting、批量读取和 projection 循环边界检查。

取消应在 2 秒内退出并释放临时对象，不返回部分 Evidence。未提供取消参数时保持现有 API 和语义。

### P1：增加按历史规模的回归基准

除现有 2,500-source synthetic parity 外，增加 100、500、1,000、2,500 sources 的真实形态基准，并分别记录：

- phase 延迟。
- P50/P95。
- 峰值 RSS。
- posting/candidate 数量。
- budget callback 次数。
- Evidence parity。

目标是确认性能随历史规模的增长来自必要的紧凑扫描，而不是正文与 Python 对象的线性物化。

## 8. 语义约束

后续优化必须继续保持：

- 与 0.8.1 相同的 activation、排序、去重和 peak 语义。
- 无预算模式完整 Evidence 逐字段一致。
- 100K Reader 可见前缀逐 token、逐字段一致。
- 跨预算边界的完整 span。
- `source_id`、`role`、`timestamp`、`text` 不变。
- 默认 projection 和 Top-K 位置不变。
- schema 3 不做静默迁移。
- 不加入数据集、query、用户或 bad-case 特判。

## 9. 下一候选的真实门槛

使用同一 1,112-request Store 和固定 query 集：

| 指标 | 0.8.1 当前值 | 下一候选目标 |
| --- | ---: | ---: |
| `search_evidence()` P50 | 184.80 s | ≤ 30 s |
| `search_evidence()` P95 | 404.01 s | ≤ 60 s |
| 单条最大值 | 489.02 s | ≤ 120 s |
| 进程峰值 RSS | 1.71 GiB | ≤ 1.0 GiB |
| 取消响应 | 不支持 | ≤ 2 s |
| 30 分钟 HTTP 断开 | 23 条/窗口 | 0 |
| Evidence parity | 已保持 | 必须保持 |

若不能一次达到最终门槛，下一版至少应证明某一个真实 phase 的成本和 RSS 明显下降，并提供相同 query 的配对 A/B；不再只以 deictic microbenchmark 或 synthetic 总时延作为发布结论。

## 10. 当前运行决策

本轮 Full 继续使用冻结的 mnemekit 0.8.1：

- 不在运行中继续更换核心版本。
- 不改变 projection、Top-K 或 100K budget。
- 持续收集真实长历史 latency、RSS 和 HTTP 状态。
- 服务失效时只通过原任务断点续跑，不新建 Full。

0.8.1 可以提供比 0.8.0 更好的基准，但下一次 Full 前仍需要解决长历史尾延迟、峰值内存和取消能力。
