# AML 第二期 Mneme5 Full 评测复盘

日期：2026-11-04\
对象：Mneme 核心实现方\
性质：评测与工程复盘；2026-11-10 按交付要求归档入库，私有评测原文和凭据除外

## 结论

Mneme 第二次 Agent Memory Leaderboard Full 已成功完成，正式成绩为
**50.7573**，相对第一次 Full 的 **44.2543** 提高 **6.5030 个百分点**。
两次任务均完成 9,602 / 9,602 道题；第二次不是因缺题、跳题或评分覆盖变化获得提升。

第二次 Full 的核心结论是：

1. Mneme5 directional successor recall 在正式外部评测中产生了显著价值，不能再视为
   仅在 STALE 或本地 proxy 上成立的研究信号。
2. Textual 从 **44.1637** 提高到 **55.7419**，提高 **11.5782pp**；综合分提升几乎
   全部来自 Textual。
3. Streaming 从 **44.3815** 小幅下降到 **43.7554**，下降 **0.6262pp**。其中
   `streaming.online` 基本持平，`streaming.intra_transfer` 下降 **4.5233pp**。
4. 一级能力中 B 提高 **12.6695pp**，D 提高 **22.9844pp**，A/E 分别提高约 6pp；
   这与 successor/revision 方法目标方向一致，但官方未提供逐题结果，不能把全部变化
   严格归因到单一内部机制。
5. H 下降 **2.8111pp**，B3、C2、E2 等子项也有明显回退。Mneme5 是必须保留的
   高价值机制，后续工作应研究适用域和准入边界，不能因局部回退整体移除。
6. Add/Search memory path 全程不使用 retrieval embedding、生成式 LLM 或 learned
   reranker。系统使用固定 spaCy `en_core_web_sm` 做 POS、lemma、NER 和 dependency
   analysis；官方统一 Reader/Judge 不属于 Mneme memory path。

这是 Mneme 当前最强的外部结果。按第一期静态榜单只作量级参考，50.76 高于第一期
开源第一 45.06 和商业第二 45.89，低于商业第一 58.02；第一期与第二期的 suite、
pipeline 和参赛集合不同，不能据此声明第二期正式名次。

## 固定参评版本

第二次 Full 从 Add 到 Eval 使用同一冻结版本，没有在任务运行中升级方法：

| 层 | 固定版本 |
| --- | --- |
| 官方系统名 / 版本 | Mneme / `v0.1` |
| API | `mneme-api==0.3.0`，tag `v0.3.0` |
| API commit | `6cd9420b612f52c8f78d5e973ae5d7cca6468003` |
| Core | `mnemekit==0.10.1`，tag `v0.10.1` |
| Core commit | `9d8d170ebf3575494c02ccb16378f60768b39a78` |
| Core method | Mneme5 directional successor recall，`ALG-DDR-1` |
| Search | `search_composed_evidence()`，`scope_owner="user"` |
| Top K | 100 source items |
| Evidence budget | 100,000 `o200k_base` tokens，按最终 API formatter 计量 |
| Store | schema 3 SQLite persistent store |

Search 返回完整原始 source，保留 `source_id`、role、timestamp 和原文；没有摘要替代、
答案生成、Top-K 后免费扩展或按 benchmark/category 路由。

## 两次 Full 总览

| 项目 | 第一次 Full | 第二次 Full |
| --- | ---: | ---: |
| Task ID | `teval_9abcb4ed9849697f` | `teval_609f7914223b606d` |
| 开始时间 UTC | 2026-09-30 14:39:55 | 2026-10-30 15:01:46 |
| 完成时间 UTC | 2026-10-11 01:55:54 | 2026-11-02 20:25:37 |
| 墙钟时间 | 约 10 天 11 小时 | 约 3 天 5 小时 24 分 |
| 状态 | succeeded | succeeded |
| 总题数 | 9,602 / 9,602 | 9,602 / 9,602 |
| Textual | 5,609 / 5,609 | 5,609 / 5,609 |
| Streaming | 3,993 / 3,993 | 3,993 / 3,993 |
| 综合分 | 44.2543 | **50.7573** |
| Textual 推算分 | 44.1637 | **55.7419** |
| Streaming | **44.3815** | 43.7554 |

Textual 分数由官方综合分、Streaming 分数和题量精确反推：

```text
overall = (5609 * textual + 3993 * streaming) / 9602
```

一级能力 A--H 是诊断切片，计数存在交叉归类，不是七个互斥桶，也不是把七个分数简单
平均得到 Overall。

第一次 Full 是有效外部基线，但运行中跨过 0.4--0.8.3 多个工程版本，且早期存在超长
payload 和服务资源问题。第二次 Full 才是固定单版本的正式 Mneme5 结果，因此两次差分
有很强价值，但不是严格的逐题 paired ablation。官方没有下发逐题答案、分数或 flip 列表。

## 正式成绩差分

### 一级能力

| 能力 | 题目计数 | 第一次 | 第二次 | 变化 |
| --- | ---: | ---: | ---: | ---: |
| A 显式事实召回 | 2,735 | 50.02 | **56.16** | **+6.13** |
| B 关系与多跳推理 | 1,944 | 32.80 | **45.47** | **+12.67** |
| C 时间与事件序列 | 1,474 | 41.03 | **44.45** | **+3.43** |
| D 记忆治理 | 1,173 | 38.63 | **61.61** | **+22.98** |
| E 个性化与关怀 | 258 | 31.88 | **38.16** | **+6.28** |
| G 上下文学习与执行 | 688 | 45.90 | **47.52** | **+1.62** |
| H 认识论安全与隐私 | 619 | **61.81** | 59.00 | **-2.81** |
| Streaming | 3,993 | **44.38** | 43.76 | **-0.63** |

### 二级能力

官方只公开二级 ID、计数与分数，没有公开这些 ID 的语义名称。下表只用于确定复现和
诊断优先级，不应按 ID 猜题型或向核心加入规则。

| ID | 计数 | 第一次 | 第二次 | 变化 |
| --- | ---: | ---: | ---: | ---: |
| A1 | 1,199 | 58.36 | 63.67 | +5.30 |
| A2 | 978 | 50.60 | 60.54 | +9.95 |
| A3 | 786 | 38.32 | 39.97 | +1.65 |
| B1 | 1,021 | 38.79 | 44.48 | +5.70 |
| B2 | 794 | 27.89 | 53.73 | **+25.84** |
| B3 | 442 | 38.05 | 31.65 | **-6.40** |
| B4 | 59 | 45.76 | 45.76 | 0.00 |
| C1 | 952 | 36.33 | 46.04 | **+9.71** |
| C2 | 359 | 52.50 | 39.44 | **-13.07** |
| C3 | 218 | 44.15 | 41.16 | -2.98 |
| D1 | 686 | 19.66 | 57.93 | **+38.27** |
| D2 | 297 | 55.68 | 67.72 | **+12.04** |
| D3 | 20 | 10.00 | 0.00 | -10.00 |
| D4 | 263 | 81.60 | 81.20 | -0.40 |
| E1 | 158 | 35.60 | 38.77 | +3.16 |
| E2 | 23 | 56.52 | 43.48 | -13.04 |
| E3 | 113 | 26.55 | 38.23 | **+11.68** |
| F1 | 64 | 18.60 | 16.97 | -1.63 |
| G1 | 313 | 52.10 | 57.13 | +5.04 |
| G2 | 118 | 57.29 | 57.25 | -0.04 |
| G3 | 40 | 35.00 | 32.50 | -2.50 |
| G4 | 132 | 17.43 | 17.14 | -0.29 |
| G5 | 117 | 50.77 | 49.61 | -1.16 |
| H1 | 463 | 69.57 | 66.65 | -2.92 |
| H2 | 156 | 38.77 | 36.28 | -2.49 |
| Streaming.online | 3,590 | 36.73 | 36.66 | -0.07 |
| Streaming.intra_transfer | 403 | 97.92 | 93.40 | **-4.52** |

## 结果应怎样解释

### 已被正式结果强化的结论

Mneme5 必须作为高价值机制保留。它在同一官方题量和能力计数下带来 +6.50pp 综合收益，
并在多个大样本切片中产生方向一致、远超 2pp 的提升。后续局部负结果只能用于限定适用域、
route 和预算，不能自动推翻该机制。

B2、D1、D2、A2、C1 和 E3 的改善最强。其中 D1 有 686 个样本且提高 38.27pp，B2 有
794 个样本且提高 25.84pp，不可能用少量小切片偶然波动解释。正式结果与 STALE sealed、
LongMemEval-S 和 legacy non-regression gate 共同支持“从旧 episode 定向恢复 later
successor”这一通用能力。

G 整体没有被新机制破坏，反而提高 1.62pp。A 也提高 6.13pp，说明新方法没有只对
revision/update 类问题有价值；它可能改善了相关 episode 的证据共同出现和 Reader 可用性。

### 尚未解决的问题

Streaming 没有获得收益。`streaming.online` 只变化 -0.07pp，可视为基本持平；
`streaming.intra_transfer` 从 97.92 降到 93.40。Mneme5 当前路线不能被描述成已经解决
Streaming online memory evolution。

H1/H2 同时下降约 2.5--2.9pp，说明 H 的回退不是单个极小切片造成。successor evidence
可能在某些问题中增加了不必要、过期、冲突或越权上下文；也可能是统一 Reader/Judge 的
运行波动。没有逐题结果时不能下结论，必须用公开 proxy 构造可复现诊断。

B3、C2、C3 也出现回退，特别是 C2 有 359 个样本且下降 13.07pp。这说明 directional
successor 对“后来证据应进入”的场景有效，但并非所有时间/关系问题都应把 later episode
前移。后续应研究 route precision、query temporal scope 和 evidence competition，不能
简单提高 successor activation 或扩大覆盖率。

E2、D3 的下降幅度大，但样本分别只有 23 和 20。它们应保留为风险信号，不应优先于
H、C2、B3 和 Streaming 的大样本诊断。

### 归因边界

可以确认的是：第二次 Full 使用固定 0.10.1，正式结果显著高于首轮；Mneme5 离线证据和
正式收益方向一致。

不能确认的是：每一道提升题是否由 successor source 直接进入 Reader 导致。首轮运行是
混合工程版本，官方也未提供逐题结果。性能、100K 有界 payload、服务稳定性和平台重试
减少也可能贡献一部分收益。因此报告把 +6.50 视为“冻结 Mneme5 系统相对首轮系统”的
外部提升，而不把它写成单一算子的严格 causal effect。

## 比赛过程与工程演进

### 第一阶段：API 接入与 Smoke

`mneme-api` 被单独建成 API wrapper，核心逻辑只从 `mnemekit` 导入。API 负责：

- 官方 Add/Search schema；
- API 鉴权；
- `user_id` 隔离；
- request ID 幂等；
- 同步 Add 可见性；
- 原始 evidence formatting；
- `o200k_base` 100K token admission；
- 本地持久化与恢复。

核心 Memory 的 activation、Evidence projection、排序和方法语义不在 API 层复制。

0.3.1、0.4.0 等早期 Smoke 暴露出 evidence projection、100K 前缀分配和运行时间问题。
这些结果用于建立指标和性能门禁，没有在 API 层按私有 case 写规则。

### 第二阶段：第一次 Full 与性能危机

第一次 Full 从 2026-09-30 运行至 2026-10-11。旧实现曾出现：

- 每个请求完整加载用户 Store；
- 2 GiB 服务器内存紧张；
- Search 单条超过 5 分钟；
- 极端返回超过 500 万 tokens；
- 2,500-source Store 的候选构造与 tokenization 放大；
- 服务重启、502 和平台 timeout；
- 首轮总共记录 12 次既往失败。

核心随后完成一系列保持 Evidence 语义的工程优化：

- 0.6：SQLite 持久索引、低内存冷开、posting 压缩与批量预取；
- 0.8：100K 有界物化，极端 5,039,038-token evidence 收敛到约 100K，并保持 Reader
  前 100K token 前缀一致；
- 0.8.1/0.8.2：预算定位由重复逐 span tokenize 改为指数探测和二分定位；
- 0.8.3：候选 source frontier 完成后停止，真实 1.57 GiB Store Search 从 365.6 秒降至
  114.9 秒，峰值 RSS 从 1,363 MiB 降至 784 MiB，Evidence hash 一致；
- 0.9.2：复用 additive item cost，真实 Store 热页 Search 降至约 4.6--4.8 秒，Evidence
  完全一致。

第一次 Full 最终成功，得到 44.2543，证明 zero-embedding / zero-generative-LLM /
zero-learned-reranker 路线有竞争力，也明确暴露 B、D1、E 和 Streaming.online 的质量缺口。

### 第三阶段：Mneme5 比赛门

Mneme5 directional successor recall 先通过：

- STALE development、opened validation 和 sealed held-out；
- 五个 Mneme1--4 legacy 数据集 source/token-budget 非退化；
- LongMemEval-S 三轮 Reader/Judge；
- MemOps 安全修订；
- 真实 1,112-history Store 性能和 Evidence parity；
- Core/API tests、wheel/sdist、PyPI 回装与 Add/Search smoke。

0.10.0 曾因 MemOps Answer 非退化门失败而判定比赛 NO-GO。0.10.1 使用通用的单 owner
episode 保留、mixed-role query admission 和稳定 evidence order 修复，不读取 benchmark、
question ID、answer 或 gold evidence，最终判定 GO。

### 第四阶段：第二次 Full

第二次 Full 使用官方 Add 16、Search 16 上限。实际部署为：

| 资源 | 配置 |
| --- | --- |
| CPU | 4 vCPU |
| RAM | 7.8 GiB |
| Swap | 8.0 GiB，最终使用 0 |
| 根盘 | 99 GiB |
| Uvicorn | 4 workers |
| 每 worker 业务并发 | 1 |
| 最大实际 Add/Search 并行 | 约 4 个进程级业务槽位 |

最终 Store 状态：

| 指标 | 结果 |
| --- | ---: |
| Store 目录 | 60 GiB |
| user store directories | 1,547 |
| Search metrics | 112 MiB |
| 任务结束磁盘余量 | 8.1 GiB |
| 任务结束可用内存 | 约 2.0 GiB |
| Swap 使用 | 0 |

磁盘空间是第二次 Full 的主要资源风险。Store 不应在官方复核前清理；复核完成后应先保留
可复现快照和脱敏统计，再处理线上磁盘。

## 第二次 Full 的平台异常

官方结果记录前三次尝试均因平台侧模型服务额度不足返回 LLM 403。AML 团队邮件确认这不是
Mneme Add/Search 的鉴权、白名单或业务错误。第四次运行继续复用原任务检查点。

任务在 98.4% 时遇到平台官网与任务 API 的 503/522 故障。平台一度把原任务错误标记为
`canceled / prepare / 0`，但 Mneme 服务始终 active，Add/Search 均为 HTTP 200。恢复后对
原 Task ID 执行一次“从断点续跑”，平台完整恢复到 9,453 / 9,602，并最终成功。

该事件证明：

- 保留原 Store、幂等请求和原 Task ID 是正确策略；
- 平台控制面故障不等于评测执行节点或 Mneme API 故障；
- 续跑必须针对原任务，不能新建重复 Full；
- 监控应同时观察平台状态和 API 实际流量，不能只看网页。

第二次 Full 最终没有记录 Mneme 业务 4xx/5xx。前三次 LLM 403 和控制面取消均应归于平台，
不能作为核心稳定性失败。

## Search、预算与真实负载

第二次 Full 的 `search-metrics.jsonl` 有 10,292 条成功记录，高于 9,602 道正式题；其中包含
Streaming、多次尝试、重试和断点续跑，不能把 metrics 行数当成独立计分题数。

### 全运行窗口

| 范围 | 数量 | P50 | P95 | P99 | 最大 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 全部 Search | 10,292 | 0.676 s | 25.659 s | 63.195 s | 537.120 s |
| history requests >= 1,000 | 240 | 58.905 s | 67.404 s | — | 337.722 s |
| 最后 200 条热页请求 | 200 | 1.530 s | 2.713 s | 3.698 s | 4.985 s |

2026-11-10 交付复算统一采用 `(n-1)*q` 线性插值，替换初稿的取整口径。逐请求数值位于
`results/aml/full2-search-metrics.jsonl`，精确统计位于 `results/aml/full2-search-summary.json`。

全窗口 P95 明显高于最终热页窗口，主要受 Add/Search 同时运行、冷页、四 worker 并发、
SQLite/云盘竞争和重试影响，不能直接解释成 0.10.1 单 query 核心算法延迟。所有请求仍低于
官方单请求 30 分钟上限。

### 按历史长度

| history requests | 数量 | P50 | P95 | 最大 |
| --- | ---: | ---: | ---: | ---: |
| `< 50` | 4,202 | 0.154 s | 4.170 s | 537.120 s |
| `50--199` | 2,910 | 1.021 s | 29.692 s | 122.556 s |
| `200--499` | 2,383 | 1.201 s | 15.863 s | 315.283 s |
| `500--999` | 557 | 2.654 s | 15.655 s | 176.682 s |
| `>= 1,000` | 240 | 58.905 s | 67.404 s | 337.722 s |

### Evidence 与 route

| 指标 | 结果 |
| --- | ---: |
| 最大 evidence tokens | **100,000** |
| 最大 response tokens | 116,046 |
| item count P50 / P95 | 100 / 100 |
| span count P50 / P95 | 100 / 100 |
| `evolution_route=true` 调用 | 8,048 / 10,292，78.2% |
| route successor source 总数 | 27,063 |
| 每个 route 调用平均 successor sources | 3.36 |

第二次 Full 没有重现首轮百万 token payload。最大 response 低于官方 117,760-token Answer
上限，100K EvidenceBudget 正常生效。

78.2% 是“成功调用行”的 route exposure，不是去重后的正式问题覆盖率。由于重试和重复
Search，不能据此声称 78.2% 的题目被 Mneme5 改写；但它说明 Mneme5 在 AML 分布上不是
稀有 no-op，route selectivity 与保护机制值得继续研究。

Add 没有在冻结部署版本中记录逐请求 phase latency，因此不能从本轮给出可靠 Add P50/P95。
当前工作区的 atomic request ledger 与 Add profile 是评测后候选，不属于这次 Full，不应把
它的本地收益写成正式运行结果。

## 给核心实现方的下一步建议

### P0：冻结并永久保留 0.10.1 结果

将以下对象作为不可覆盖的正式基线：

- `mnemekit==0.10.1` / `9d8d170`；
- `mneme-api==0.3.0` / `6cd9420`；
- 官方 Task ID 与完整 aggregate result；
- 第二次 Full Store 的只读快照或可恢复副本；
- 脱敏 Search metrics 聚合；
- STALE、legacy、MemOps、LongMemEval-S 和真实 Store gate。

Mneme5 已达到高价值结果保留标准。后续不得因某个小切片或单一 proxy 回退而直接删除；
应通过 route、scope、预算和证据竞争研究其适用边界。

### P1：优先保护 H

H1/H2 均下降，应建立不依赖 AML 私有标签的公开诊断：

- 无证据和证据不足；
- conflicting sources；
- historical 与 current scope；
- owner/identity 边界；
- sensitive information 与拒答；
- later successor 是否被错误当成 query 所需证据。

指标应同时报告 source precision、unsupported successor exposure、Evidence digest、Reader
答案和 Judge，不要通过全局降低 successor activation 粗暴修复。

### P2：单独研究 Streaming

`streaming.online` 基本不变，说明当前 episode successor 不能代替完整增量状态语义。应按
真实 Streaming 协议构造每次 Add 后立即 Search 的回放，记录：

- add-to-search visibility；
- 当前、历史和变化 query 的 source sequence；
- correction/retraction/supersession；
- obsolete evidence exposure；
- intra-transfer source preservation；
- 相同 query 随 Add 的 Evidence digest 演化。

Streaming 路线应与 Mneme5 保留机制分开实验，不要一次合入新的 persistent suppression。

### P3：定位 B3 与 C2 的适用域

B 总体大幅提高但 B3 下降，C1 提高而 C2/C3 下降，说明 query scope 或 path completion
存在分化。建议在公开多跳、时间和 as-of 集上比较：

- direct evidence 与 bridge evidence 的共同覆盖；
- later successor 对历史问题的错误前移；
- relation direction；
- source owner 与 mixed-role packet；
- Top-10/20/40 和 8K/24K/100K 下的 Complete/precision；
- route 内与 route 外的 paired win/loss/tie。

不要根据 B3/C2 ID 写规则，也不要继续提高全局 route coverage。目标是识别通用语义边界。

### P4：继续做工程降本，但与方法版本解耦

正式 Full 已证明 0.10.1 可在 8 GiB / 4 worker 上稳定完成，但仍有产品化问题：

- 60 GiB Store 对 100 GiB 根盘过重；
- 1,000-history Search P50 仍接近 59 秒；
- 全窗口存在 5--9 分钟长尾；
- 四 worker 复制常驻状态，总 RSS 约 5 GiB；
- SQLite/云盘在 Add/Search 并发阶段有明显 I/O 竞争；
- metrics 的完整 source ID 列表造成 112 MiB 额外写入。

建议继续验证 atomic request ledger、单事务 Add、posting 批量读取、有限热索引、metrics digest
和 bounded cache。所有工程版本必须先证明 Evidence 字段、顺序、评分和 Reader 可见前缀与
0.10.1 一致，再替换生产版本。

## 不能从本轮推出的结论

- 不能宣称第二期正式第一；官方榜单尚未发布且需要材料与结果复核。
- 不能把第一期榜单与第二期分数当成同一参赛集合的严格排名。
- 不能把 +6.50 全部写成 successor activation 的单算子因果效应。
- 不能根据 B2、D1、C2 等私有 ID 猜测具体题型并写规则。
- 不能说 Mneme 完全“无模型”；memory path 不用 retrieval embedding、生成式 LLM 和
  learned reranker，但固定 spaCy pipeline 包含统计 NLP 组件。
- 不能说 Streaming 已解决；正式结果显示它没有改善。
- 不能用完整 metrics 行数推断受影响正式题数；其中包含重试和断点续跑。
- 不能在官方复核前删除 Store、请求幂等记录或任务相关运行状态。

## 最终判断

Mneme5 0.10.1 应正式升级为当前质量基线。它把同一官方 9,602-question Full 从 44.25
提高到 50.76，在不使用 retrieval embedding、生成式 LLM 或 learned reranker 的前提下，
显著改善了事实、多跳、治理和个性化能力，同时保持 G。

下一阶段不应盲目扩大召回或推翻 successor recall。最有价值的工作是：保留已经成立的
Mneme5 主机制，精确限定 H、Streaming、B3 和 C2 暴露出的适用边界，并把 Store、长历史
延迟和 Add 写放大作为独立工程版本处理。

## 数据来源

- AML evaluation API：两次 Full 的 aggregate result、capability、subcapability、状态与
  previous failures；
- 第二次 Full `search-metrics.jsonl`：10,292 条成功调用；
- 远端 systemd、memory、swap、disk 与 Store 只读检查；
- 第一轮复盘：`reports/aml-full-final-analysis-and-next-run-20261011.md`；
- Mneme5 比赛门：`reports/mneme5-competition-upgrade-gate-20261024.md`；
- 0.6--0.9.2 性能与真实 Store 报告；
- Mneme core release tag `v0.10.1` 与 API tag `v0.3.0`。

报告不包含 LDBD Key、API token、服务密钥、评测原文、私有 query 或完整 source ID。
