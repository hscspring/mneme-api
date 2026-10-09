# mnemekit 0.6.0 Full 长历史 Search 性能报告

日期：2026-10-09  
来源：Agent Memory Leaderboard 文本赛道 Full 评测  
评测任务：`teval_9abcb4ed9849697f`  
核心版本：mnemekit 0.6.0，Git tag `v0.6.0`，commit `2c3b2be`  
API 版本：mneme-api 0.1.12

## 1. 结论

mnemekit 0.6.0 已经解决此前最严重的 Store 冷启动和常驻内存问题，但 Full 的长历史 Search 暴露了新的主瓶颈：`Memory.search_evidence()` 的工作量和返回体没有被 `topn` 有效约束。

当前最重用户有 1,112 个已完成 Add 请求。对该用户的 Search：

- `topn=100` 实际只返回 1–5 个 `EvidenceItem`。
- 每次都物化 2,500 个 `EvidenceSpan`。
- 返回 JSON 约 547 万 `o200k_base` tokens，其中 evidence 正文约 485 万 tokens。
- 当前稳定进程内 22 次成功 Search 的核心调用 P50 为 285 秒，P95 为 334 秒。
- Store 加载 P50 只有 1.0 秒，API 格式化 P50 只有 0.19 秒。
- 单请求运行时 RSS 从约 0.8 GiB 上升到 1.6–1.7 GiB；2 GiB 主机的可用内存最低降至约 44 MiB，并开始使用 Swap。

因此，这次问题不是 0.5 时代的 Store 全量加载，也不是 API 调度造成的主要计算耗时。主耗时明确位于 `search_evidence()` 调用内部。结合 0.6.0 代码，最可能的结构性原因是 tag projection 对每个入选 tag 的全部 postings 做预取、排序和 span 物化，而 `topn` 只限制最终 item 数，不限制 item 内的 span 数和 token 数。

当前 Full 不应中途改变检索行为。建议让它用冻结的 0.6.0 继续完成；优化在下一版本离线实现，并以 Reader 可见前缀一致性作为质量门禁。

## 2. 运行环境与口径

| 项目 | 配置 |
| --- | --- |
| CPU | 2 vCPU，AMD EPYC 7A23 |
| 内存 | 2,014,468 KiB，约 1.92 GiB |
| Swap | 8 GiB |
| API 业务并发 | 1，Add 和 Search 共用 `BoundedSemaphore(1)` |
| Uvicorn worker | 1 |
| 平台并发上限 | Add 16、Search 16 |
| Search 调用 | `memory.search_evidence(query, topn=100)` |
| projection | 0.6.0 默认 `TAG_GRAPH_DEDUP` |
| Reader 上限 | evidence 前 100,000 tokens |

API 每次 Search 记录以下分段耗时：

- `load_ms`：用户锁、journal 恢复和 `Memory` 打开。
- `search_ms`：完整的 `memory.search_evidence()`。
- `format_ms`：将 `EvidenceItem` 转成 API response model。
- `total_ms`：以上三段之和。

`total_ms` 不包含诊断日志中的 tiktoken 计数，也不包含 ASGI JSON 编码和网络发送。报告因此只把 `search_ms` 作为核心耗时的直接证据；诊断计数和 HTTP 序列化属于后续仍需单独压缩的 API 开销。

## 3. 当前稳定进程实测

当前服务进程启动于 2026-10-09 13:45:10（UTC+8）。截至 15:35:58，共完成 24 次 Search，其中 22 次来自同一个 1,112 请求长历史用户。该窗口内版本、进程和并发配置保持不变。

### 3.1 延迟

| 阶段 | 最小 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: |
| Store 加载 | 0.016 s | 0.996 s | 2.159 s | 29.737 s |
| `search_evidence()` | 114.516 s | 285.065 s | 334.040 s | 383.425 s |
| API response model 格式化 | 0.075 s | 0.189 s | 1.195 s | 1.333 s |
| API 已计时总延迟 | 114.668 s | 286.796 s | 362.725 s | 385.095 s |

P50 请求中，`search_evidence()` 占已计时总延迟约 99%。重新创建 `Memory` 的成本已经不是主要问题。

### 3.2 返回规模

| 指标 | 最小 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: |
| EvidenceItem 数 | 1 | 2 | 3 | 5 |
| EvidenceSpan 数 | 2,500 | 2,500 | 2,500 | 2,500 |
| response tokens | 5,467,774 | 5,467,814 | 5,467,852 | 5,467,920 |
| 完整 item 的前缀 tokens | 0 | 3,786 | 71,214 | 80,372 |
| 完整 item 的 span 覆盖率 | 0% | 0.08% | 1.52% | 1.76% |

`完整 item 的前缀`只统计在 100k 边界前能够完整放下的 item。若第一个 item 自身超过 100k，平台仍会从该 item 内截断，因此该值可能为 0。

无论如何，Reader 最多使用前 100k tokens，只占约 485 万 evidence tokens 的 2.1%。核心却已经为其余约 98% 的内容完成 postings 读取、trace 预取、排序、span 物化和 Python 对象分配，API 随后还要把它们拼接进约 547 万 tokens 的 JSON response。

### 3.3 内存曲线

连续观测到的典型单请求周期如下：

| 状态 | API RSS | VmSwap | 系统可用内存 |
| --- | ---: | ---: | ---: |
| 请求结束后 | 0.77–0.80 GiB | 0.26–0.30 GiB | 0.90–0.92 GiB |
| 请求运行约 4–5 分钟 | 1.56–1.64 GiB | 0.25–0.34 GiB | 44–87 MiB |

请求结束后 API 0.1.12 释放 `Memory` 并执行 GC，RSS 会明显回落，说明没有持续累积的跨请求缓存泄漏。风险来自单个 Search 自身的峰值对象规模。健康接口在这些采样点仍返回 HTTP 200，但 SSH 和只读统计也会明显变慢。

2 GiB 主机无法安全增加 worker：两个同时达到同类峰值的 Search 足以触发 OOM 或严重 Swap 抖动。因此平台虽然允许 Search 16 并发，当前只能串行处理。

## 4. 跨重启佐证

完整 metrics 文件包含多个 API/核心版本和多次恢复过程，不能作为单一干净基准。只筛选同一个 `history_requests=1112` 的长历史形态后，共有 227 次成功记录：

| 指标 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: |
| `search_evidence()` | 338.786 s | 691.350 s | 3,617.651 s |
| Store 加载 | 1.099 s | 7.228 s | 94.387 s |
| 格式化 | 0.187 s | 5.275 s | 13.282 s |
| 已计时总延迟 | 348.109 s | 695.151 s | 3,627.194 s |

这些历史记录受机器重启、内存压力和旧 API 生命周期影响，不能替代当前进程的 22 次窗口；但它们证明该数据形态在不同尝试中都持续触发分钟级 Search，且极端情况下超过平台单请求 30 分钟上限。

## 5. 0.6.0 代码层原因

分析以发布 tag `v0.6.0` 为准，没有使用当前 main 上尚未发布的实现。

`mneme/memory.py` 的 `Memory.search_evidence()` 先运行 activation，再将完整 activated 列表交给 `EvidenceProjector`。默认 projection 是 `TAG_GRAPH_DEDUP`。

`mneme/evidence.py` 的 tag projection 对每个候选 tag 执行：

1. 从倒排索引读取该 tag 的全部 postings。
2. 对所有 postings 去重得到 `unit_ids`。
3. 为当前 tag 预取全部 unit。
4. 为这些 unit 涉及的全部 source 预取 trace。
5. 对全部 `unit_ids` 排序。
6. 对保留 source 逐个调用 `_span()` 并组成一个 `EvidenceItem`。
7. 完整 item 构造完成后，才检查 EvidenceItem 数是否达到 `topn`。

这导致 `topn=100` 只表示“最多 100 个 tag item”，不表示“最多 100 个原始 turn/span”，也不构成 token 或内存上限。一个高频 tag 可以在单个 item 中包含整个长历史的数千个 span。`TAG_GRAPH_DEDUP` 会跨 item 去除重复 source，但不会限制第一个 item 内的 source 数。

当前指标与这条路径吻合：item 数仅 1–5，span 数却固定为 2,500；item 越少并没有减少返回规模。

现有数据还不能把 `search_evidence()` 内部时间精确拆成 activation、candidate tag、posting 读取、prefetch、排序、`_span()` 和 cache clear。实现优化前应先给离线 benchmark 增加这些 phase timing，避免只凭总耗时猜测某一个子阶段。

## 6. 对比赛和业务的影响

1. 当前稳定速度约为每 4.8–5.6 分钟完成一个重 Search，即每小时约 11–12 个。
2. 平台并发 16 无法转化为吞吐，因为单请求峰值内存迫使 API 串行。
3. 历史极端值超过 60 分钟，已经高于平台 30 分钟单请求上限。
4. 返回约 547 万 tokens，而下游只读取前 100k，绝大多数计算、对象和网络流量没有进入评分。
5. 对普通在线业务，分钟级检索延迟和 GiB 级单请求峰值都不可接受；不使用 embedding/LLM 本应带来低延迟和低成本，目前这一优势尚未兑现。

## 7. 核心改进需求

### P0：让 evidence projection 有真实的工作量上限

核心应同时支持 item、span 和内容预算。预算必须在 trace 正文预取和 `EvidenceSpan` 物化之前生效，不能先构造完整 EvidenceItem 再截断。

接口形态由核心库决定，但应能表达以下约束：

- 最多返回 `topn` 个 item。
- 最多物化给定数量的 span/source。
- 最多产生给定内容预算，或支持 API 按 token budget 惰性消费。
- 达到预算后不再读取和构造不可见后缀。

mnemekit 可以继续保持 tokenizer 无关；例如提供确定性的 span/字符预算或惰性迭代器，由 API 负责 100k token 边界。关键是核心不能为最终不会返回的数千个 span 读取正文并创建对象。

### P0：保持 Reader 可见前缀语义

比赛优化不应简单改成另一种召回结果。对相同 Store、query 和 projection，优化路径在预算内应保持：

- EvidenceItem 排序一致。
- item 内 source/span 排序一致。
- `source_id`、`role`、`timestamp`、`text` 一致。
- Reader 可见的前 100k tokens 与 0.6.0 完整输出一致。

允许省略的只有 Reader 永远不可见的后缀。若核心采用 span/字符预算而无法天然保证 token 前缀，应由 API 做固定 query 集的 100k token 严格 parity 验证。

### P0：先选择，再物化

建议将 projection 分为两个阶段：

1. 使用紧凑 posting、activation strength、source ID 和必要的排序元数据确定候选顺序及预算内 source。
2. 只批量预取最终保留 source 的 unit/trace，并物化 span。

即使为了保持精确排序仍需检查全部 posting，也不应加载全部正文、创建全部 `EvidenceSpan` 或拼接全部内容。

### P1：增加核心 phase benchmark

离线 benchmark 至少记录：

- activation。
- candidate tag 枚举。
- posting 读取。
- unit/trace prefetch。
- item 内排序。
- span 物化。
- cache clear。
- 总峰值 RSS。

基准应覆盖高频 tag、1 个大 item、多个中等 item，以及不同历史规模，避免只测 item 数较多但单 item 很小的样本。

## 8. 建议验收门槛

使用合成数据构造与当前形态等价的单用户 Store：约 1,112 个 Add 请求、2,500 个可检索 source，并让查询命中覆盖全部 source 的高频 tag。

在 2 vCPU、2 GiB RAM、单 worker 上验收：

| 门槛 | 目标 |
| --- | ---: |
| Reader 可见前 100k token parity | 逐 token/逐字段一致 |
| `search_evidence()` P50 | ≤ 5 s |
| `search_evidence()` P95 | ≤ 10 s |
| 单 Search 峰值 RSS | ≤ 1.2 GiB |
| API 返回 evidence | ≤ 100k tokens 加一个完整边界 span，且硬上限 ≤ 120k |
| 30 分钟超时 | 0 次 |

同时保留无预算模式用于通用 API 兼容性，但比赛路径必须显式使用有界模式。性能增长应主要与保留预算相关，而不是与高频 tag 的完整 posting 数和全部历史正文线性相关。

## 9. API 侧后续动作

核心有界接口发布后，API 侧需要：

1. 显式传入与 Reader 100k tokens 对齐的预算。
2. 在固定 Store/query 上比较 0.6.0 完整输出与新实现的 Reader 可见前缀。
3. 重新执行 Smoke，确认召回评分没有回退。
4. 记录端到端延迟、核心 phase、HTTP response 大小和峰值 RSS。
5. 缩减当前诊断日志：metrics 文件已达到约 633 MB；避免记录大 source ID 数组，并避免为统计再次 tokenize 整个 547 万 token response。

当前 Full 完成前，不在生产服务上更换核心版本、projection、Top-K 或 evidence 截断规则。
