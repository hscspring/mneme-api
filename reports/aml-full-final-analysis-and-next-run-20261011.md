# AML Full 首轮结果、运行复盘与下一轮提分建议

日期：2026-10-11

任务：`teval_9abcb4ed9849697f`

系统：Mneme v0.1，学术榜

最终分数：**44.2543**

最终状态：**succeeded，9,602 / 9,602**

## 结论

首轮 Full 已经证明 Mneme 的无 LLM、无 embedding 检索路线具有竞争力。44.25 不是一个只能工作的接入分，而是接近用户保存的榜单快照第一梯队：按该快照静态比较，大致位于第 7 名，距离 45.06 的第一名约 0.81 分。由于本轮加入 Streaming、榜单尚未最终发布，这个名次只能用来判断量级，不能作为正式排名。

0.8.3 已基本解决本轮暴露的性能阻塞。最终 2,932 条线上 Search 的 P50/P95/P99 为 1.15/2.93/16.44 秒，最慢 43.05 秒；1,112-history 极端 Store 的 P50/P95 为 22.89/32.76 秒。下一阶段可以继续做长历史性能优化，但它不再是当前最有价值的主线。

下一轮最值得投入的是证据排序与组织：

1. 优先验证 `EXP-APP`，因为它保持 activation frontier，又改善 graph-reachable tail 的组织和预算覆盖，已有跨数据集 recall 与冻结 Reader/Judge 证据支持。
2. 针对 **B 关系与多跳、E 个性化、Streaming.online** 建立离线诊断集，测 joint evidence coverage、时间有效性、冲突更新和 Reader 可用性。
3. 不再扩大 100K 召回宽度。现有离线结果显示 100K recall 已接近饱和，gold-only 诊断也表明主要损失已经转向证据组织和长上下文利用。
4. 第二次 Full 应从 Add 开始冻结一个版本跑到底。首轮中途跨过多个工程版本，适合作为有效基线，但不适合作为严格的单版本方法对比。

仅靠 0.8.x 的性能等价优化，第二次 Full 有机会消除超长返回带来的边界不确定性，成绩可能小幅变化；没有证据支持仅凭性能修复就一定获得明显提分。要稳定超过首轮，需要方法层面的证据组织改进。

## 官方结果

### 总体与两条分支

| 指标 | 结果 |
| --- | ---: |
| 综合分 | **44.2543** |
| 完成题数 | 9,602 / 9,602 |
| Textual | 5,609 / 5,609 |
| Streaming | 3,993 / 3,993 |
| Streaming 分数 | 44.3815 |
| 推算 Textual 分数 | 44.1637 |
| Add cache 复用 | 38,168 chunks |

Textual 分数由总体分、Streaming 分数和各自题数加权反推，官方结果对象没有单独返回该字段。

### 一级能力

| 能力 | 分数 | 官方计数 | 判断 |
| --- | ---: | ---: | --- |
| A 显式事实召回 | 50.02 | 2,735 | 中上，仍有长尾事实空间 |
| B 关系与多跳推理 | **32.80** | 1,944 | 主要短板 |
| C 时间与事件序列 | 41.03 | 1,474 | 中等，有明显子类差异 |
| D 记忆治理 | 38.63 | 1,173 | 总体偏低，但内部强弱分化很大 |
| E 个性化与关怀 | **31.88** | 258 | 主要短板 |
| G 上下文学习与执行 | 45.90 | 688 | 总体较好，存在单个弱子类 |
| H 认识论安全与隐私 | **61.81** | 619 | 最强一级能力 |
| Streaming | 44.38 | 3,993 | 迁移强，在线更新弱 |

官方各一级能力的计数之和可能包含评测内部的交叉归类，不能直接用“子类加若干分”线性换算综合分。

### 二级能力

官方接口只公开二级 ID、分数和计数，没有公开这些 ID 的语义名称。下表因此只用于找诊断优先级，不把 ID 擅自解释成具体题型。

| ID | 分数 | 计数 | ID | 分数 | 计数 |
| --- | ---: | ---: | --- | ---: | ---: |
| A1 | 58.36 | 1,199 | A2 | 50.60 | 978 |
| A3 | **38.32** | 786 | B1 | 38.79 | 1,021 |
| B2 | **27.89** | 794 | B3 | 38.05 | 442 |
| B4 | 45.76 | 59 | C1 | **36.33** | 952 |
| C2 | 52.50 | 359 | C3 | 44.15 | 218 |
| D1 | **19.66** | 686 | D2 | 55.68 | 297 |
| D3 | 10.00 | 20 | D4 | **81.60** | 263 |
| F1 | **18.60** | 64 | E1 | 35.60 | 158 |
| E2 | 56.52 | 23 | E3 | **26.55** | 113 |
| G1 | 52.10 | 313 | G2 | 57.29 | 118 |
| G3 | 35.00 | 40 | G4 | **17.43** | 132 |
| G5 | 50.77 | 117 | H1 | **69.57** | 463 |
| H2 | 38.77 | 156 | Streaming.online | **36.73** | 3,590 |
| Streaming.intra_transfer | **97.92** | 403 |  |  |  |

从“低分且样本量大”看，首批诊断顺序应是：`Streaming.online`、`B2`、`D1`、`C1`、`A3`，再看 `E3` 和 `G4`。`D3`、`F1` 分数虽低，但样本较少，只有在确认语义与通用机制一致后才值得优先投入。

## 这次 44.25 应怎样解释

### 它是有效基线，但不是干净的单版本基线

任务从 2026-09-30 14:39:55 UTC 运行到 2026-10-11 01:55:54 UTC，墙钟时间约 10 天 11 小时。期间包含暂停、断点续跑、服务重启和工程版本升级，不能把墙钟时间当作最终版本的实际吞吐。

官方记录了 12 次既往失败：

| 类型 | 次数 | 归属判断 |
| --- | ---: | --- |
| Search 502 | 6 | 主要是服务承载与进程不可用 |
| Search timeout | 3 | 主要由旧版本长查询和资源压力触发 |
| Add 502 | 1 | 服务可用性问题 |
| Search 401 / 上游 token validation | 1 | 错误中嵌套 LLM 网关信息，不能归因于 Mneme 核心 |
| 官方 evaluator runtime error | 1 | 平台评测阶段错误 |

最终 9,602 题全部完成，因此首轮不存在“少答了一批题导致分数偏低”的证据。此前失败主要影响耗时和运维，不应被核心实现方当成算法短板。

### 超长返回会带来不确定性，但无法量化影响题数

0.8.0 预算物化上线前，日志中存在大量超过官方 Answer 输入上限的成功 Search：

- 3,326 条成功核心调用的 `response_tokens > 117,760`；
- 413 条超过 100 万 tokens；
- 238 条超过 500 万 tokens；
- 已观察到 2,500 spans、约 484 万 evidence tokens、约 547 万 response tokens 的极端返回；
- 这些记录集中出现在 10 月 5 日至 10 月 9 日。

这里的 3,326 不能解释为 3,326 道正式题受影响。Search metrics 同时包含平台重试、断点续跑和重复调用，总记录数 10,807，高于正式题数；旧日志也没有 request ID 或 query hash，无法把一次核心调用与最终被平台缓存、送入 Reader 的那次调用精确对应。

0.8.0 以后按 API Evidence 格式执行 100K token 预算。核心方复现的极端案例从 2,500 spans / 5,039,038 tokens 收敛到约 50 spans / 100,788 tokens，并保持前 100,000 个 `o200k_base` tokens 及 Evidence 顺序前缀一致。0.8.3 线上窗口的最大 response 为 115,231 tokens，全部低于 117,760。

因此，干净的 0.8.3 重跑有两个可能收益：

1. 所有题都以一致的、有界 Evidence 进入 Reader，不再依赖平台对超长返回的截断与序列化行为。
2. 边界 span、问题/prompt 预留空间和失败重试更可控，减少非算法噪声。

但 0.8.x 特意保持 Reader 可见的 100K 前缀，因此性能修复本身不应被当成一次大幅提分机制。没有逐题绑定数据，无法估计首轮究竟有多少计分答案因超长返回受损。

## 性能问题已经解决到什么程度

### 最终 0.8.3 线上窗口

| 指标 | 全部 0.8.3 Search | 1,112-history Search |
| --- | ---: | ---: |
| 样本数 | 2,932 | 34 |
| P50 | **1.15 s** | **22.89 s** |
| P95 | **2.93 s** | **32.76 s** |
| P99 | 16.44 s | 38.60 s |
| 最大值 | 43.05 s | 43.05 s |
| 超过 120 s | 0 | 0 |

按历史长度拆分：

| history requests | 数量 | Search P50 | Search P95 | 最大值 |
| --- | ---: | ---: | ---: | ---: |
| `< 50` | 1,127 | 0.030 s | 0.930 s | 1.960 s |
| `50–199` | 1,068 | 1.337 s | 2.925 s | 11.978 s |
| `200–499` | 642 | 1.902 s | 2.993 s | 4.960 s |
| `500–999` | 61 | 2.695 s | 3.624 s | 4.766 s |
| `>= 1000` | 34 | 22.888 s | 32.760 s | 41.318 s |

0.8.3 全窗口中 2,896 / 2,932 条不超过 5 秒，全部不超过 60 秒。1,112-history 的非配对线上统计从 0.8.2 的 P50 294.82 秒降到 22.89 秒，约快 12.9 倍；核心方同 query 离线配对测试为 365.6 → 114.9 秒、Evidence hash 完全一致。两组测量口径不同，应同时保留，不能用线上非配对倍数替代严格配对结果。

### 仍值得做的工程优化

性能已经不再阻塞下一轮 Full，但产品化仍有空间：

- 1,112-history 查询仍需要读取约 2,500 traces 和 2,500 peak units；连续热索引或新 schema 可能继续降低 20–40 秒长尾。
- 2 GiB 机器最终约 1.03 GiB RSS、约 1.36 GiB VmHWM，稳定但留给并发的余量不大。
- 建议分阶段记录 activation、posting read、peak selection、materialization、budget 等耗时，区分冷页、对象解码与图遍历。
- 建议给 Search 增加协作式 deadline/cancellation，避免客户端已经放弃后继续占用唯一业务槽位。
- 缓存必须有明确上限，不能用常驻全部 trace/unit 换延迟。

这些优化应继续遵守 Evidence digest parity；不要与方法升级绑在同一个版本中，否则第二次 Full 无法区分质量变化来源。

## 下一阶段的质量判断

### 召回宽度已经不是主要问题

现有核心离线结果显示，在统一 100K token 预算下，canonical source recall 为：LoCoMo 100.00、LME-S 99.93、BEAM-100K 95.68。`EXP-APP` 为 100.00、100.00、98.55。

冻结 Reader 的 gold-only 诊断进一步表明：

- LoCoMo 24K 从 62.60 accuracy / 54.04 F1 提升到 67.66 / 57.79；
- LME-S 从 54.40 / 46.28 提升到 68.40 / 59.66；
- LME-S 470 个可回答问题中，461 个已经把全部 gold evidence 放入 Reader 输入。

这组证据说明，尤其在 LME 类长记忆任务中，继续添加更多候选的边际收益很低。主要问题是相关证据怎样排列、怎样形成可读的多证据 packet，以及无关但高激活内容是否挤占 Reader 注意力。

### 首选候选：`EXP-APP`

`EXP-APP` 是当前最有证据支持的下一候选，因为它保持 activation frontier，不增加 embedding、LLM、reranker、阈值或数据集路由，只重组 graph-reachable tail：

| 数据集 | Recall@10 | 24K recall | 100K recall |
| --- | ---: | ---: | ---: |
| LoCoMo | 69.46 | 94.65 | 100.00 |
| LME-S | 84.33 | 98.59 | 100.00 |
| BEAM-100K | 50.56 | 72.21 | 98.55 |

相对 atomic 0.4 canonical 的 8K/24K/100K 九格门禁中，`EXP-APP` 全部不退化、八格提升。24K 的 Qwen3.6-27B Reader / MiniMax-M3 Judge 诊断也显示，它相对 grouped lexical control 在 LoCoMo 和 LME-S 都有明显提升。

它仍不能直接成为下一次 Full 版本。现有 control 不是 Paper1 的完整算法，且 AML 的私有分布与 LoCoMo/LME/BEAM 不同。上线前仍要按核心仓库冻结协议通过 Paper1-continuity、跨数据集不退化和多次 Reader/Judge 稳定性检查。

## 面向薄弱能力的通用研究方向

以下都是从聚合分数和现有离线证据形成的假设。官方没有逐题输出，也没有公开二级 ID 含义，因此不能直接按榜单类别写规则。

### 1. B：多证据联合覆盖与路径可读性

B 为 32.80，B2 为 27.89 且有 794 个样本，是最明确的高价值方向。建议新增三类 reader-free 指标：

- `Complete@K`：回答所需的全部 source 是否同时进入预算；
- bridge coverage：连接两个实体或事件的中间 source 是否进入同一 packet；
- path compactness：完成一条证据链需要穿过多少无关 spans 和 tokens。

机制方向应从现有 `cue → source` activation responsibility 推导，使同一关系链上的多个独立 source 在预算内共同存活。不要在 Top-K 后按人物名或关系词补邻居，也不要为“多跳题”增加题型路由。

### 2. E：偏好的时间有效性与冲突状态

E 为 31.88，E3 为 26.55。建议把重复偏好表示成带 provenance 的状态序列，显式保留：

- 当前陈述与历史陈述的时间顺序；
- 肯定、否定、撤回和替代关系；
- preference owner 与作用对象；
- 当前有效证据和被更新证据之间的可追溯关系。

Search 仍应通过统一 activation field 选择证据，而不是在输出端做“最新一句优先”的固定规则。先在 LoCoMo/LME 可映射样本上测 temporal-valid Complete@K，再进入 Reader。

### 3. Streaming.online：增量状态演化

`streaming.intra_transfer` 达到 97.92，而 `streaming.online` 只有 36.73。这个差异说明 Mneme 的跨段保留和可访问性很强，在线发生新增、修正、覆盖或失效时的状态演化更值得检查。

建议构造与真实 Streaming 协议一致的增量回放：每次 Add 后立即 Search，记录答案依赖 source 的首次出现、更新、冲突与失效。核心指标包括：

- add-to-search visibility；
- revision survival 与 obsolete evidence suppression；
- 相同 query 在每一步的 Evidence digest 演化；
- 新事实加入后旧高激活 source 是否持续占据前缀。

该方向可能同时改善 D 和 E，但必须通过通用 update/revision 语义实现。

### 4. C/A：时间规范化、主体绑定和隐式事实

C1 36.33、A3 38.32，且样本量分别为 952 和 786。建议在 proposition/frame 层检查：

- 相对时间与绝对时间是否归一到可比较事件；
- pronoun、owner、speaker 和被描述主体是否稳定绑定；
- 同一事实分散在 user/assistant response pair 时，因果恢复是否保留正确 source；
- 等强度 source 的长度 tie-break 是否会把关键长句长期推到预算边界外。

先用冻结标注做 source attribution，只有当同一种结构性缺口跨 LoCoMo、LME、BEAM 同时出现，才修改 formation 或 activation。

### 5. D/G/H：先识别语义，再决定是否改核心

D1、G4、F1 很低，但 D4、G1、G2、G5、H1 已经很强。一级能力内部反差意味着统一扩大或压缩 evidence 很可能同时伤害强项。

在拿到官方二级定义或可映射的本地 annotations 前，不建议根据 `D1`、`G4` 这些 ID 猜规则。先建立 ID 到本地能力标签的审计映射，再判断缺口属于检索、状态治理、Reader 指令执行还是评测安全策略。H1 69.57 是需要保护的明确优势。

## 推荐的下一轮实验顺序

### Gate 0：冻结当前基线

- 固定 `mnemekit==0.8.3`、projection、Top-K、100K EvidenceBudget、tokenizer 和 API formatter。
- 保存 LoCoMo、LME-S、BEAM 的 source sequence、Evidence digest、token count 和下游结果。
- 对 Reader/Judge 至少重复运行三次，报告均值、标准差和 paired win/loss/tie。

### Gate 1：证据归因诊断

- 按 A/B/C/D/E/G/H 可映射能力，对错误样本分成 missing、present-but-late、present-but-diffuse、contradicted、stale、reader-failed。
- 同时报告 Recall/Any/Complete@10/20/40 和 8K/24K/100K。
- 对 B 类额外报告 bridge/path coverage；对 Streaming 报告每一步 Evidence digest 演化。

### Gate 2：`EXP-APP` 配对比较

- 先做 reader-free 全量 gate，要求 LoCoMo/LME-S/BEAM 所有冻结格不退化。
- 再用完全相同的 Qwen3.6 Reader、MiniMax-M3 Judge、prompt、temperature 和样本顺序跑下游。
- 重点观察 B/E/Streaming proxy，同时要求 A/C/G/H 无实质退化。
- 如果收益只来自更大 payload，应判为预算变化，不判为方法提升。

### Gate 3：只保留一个方法变量

第二次 Full 只部署通过门禁的一个方法候选。性能优化可以继续合入，但必须先证明 Evidence digest parity。不要在 Full 运行中升级版本，不再产生混合 checkpoint。

### Gate 4：加强可观测性

下一次 metrics 至少增加：

- `request_id` 或不可逆 query hash；
- `mnemekit_version`、projection、budget 和 schema；
- activation/posting/peak/materialization/budget 分阶段耗时；
- Evidence digest 与最终 source ID prefix digest；
- 是否被重试、客户端是否断开、HTTP 最终状态。

当前 metrics 把完整 source ID 数组写入每条记录，最终文件约 746 MB。下一轮保留 count、digest 和少量边界样本即可，避免监控本身制造磁盘与 I/O 压力。

## 不应从本轮推出的结论

- 不能说有 3,326 道正式题被超长返回影响；这个数字包含重试和断点续跑。
- 不能把 44.25 与旧榜单直接认定为正式第 7；赛制、Streaming 和最终参赛集合可能不同。
- 不能根据聚合 ID 推断 D1、G4 等子类的具体语义。
- 不能把 0.8.3 的约 12.9 倍线上 P50 提升当作严格同 query 算法对比；严格配对结果是核心方的 3.18 倍和 Evidence parity。
- 不能认为 100K recall 高就等于答案质量已经封顶；gold-only 与 AML 分数都说明 Evidence organization 和 Reader utilization 仍有明显差距。
- 不能保证干净的 0.8.3 重跑一定高于 44.25。它首先提高的是一致性和可复现性，明显提分仍需要经过门禁的方法改进。

## 给核心实现方的直接建议

把 44.25 作为可信的第一条外部基线。0.8.3 已让工程性能从主要风险降为可继续优化的长尾问题。研究主线应转向 `EXP-APP` 的严格晋级验证，以及 B/E/Streaming.online 对应的多证据组织、状态更新和冲突语义。

下一版本最理想的结果不是再召回更多原文，而是在不改变统一 activation 主链、不引入模型和数据集规则的前提下，让同样的 100K Evidence 更紧凑、更具关系结构、更能表达当前有效状态。只有这个方向同时提升冻结 Reader/Judge，并保护 H、A、G 的现有优势，才值得用于第二次 Full。

## 数据来源与边界

- 官方任务结果：2026-10-11 拉取的 evaluation result 和 private result aggregate。
- 线上 Search metrics：10,807 条，2026-09-29 至 2026-10-11，约 746 MB。
- 版本窗口：0.8.1 于 2026-10-10 01:46 UTC、0.8.2 于 03:19 UTC、0.8.3 于 09:09 UTC 部署。
- 核心离线证据：Mneme `HANDOFF.md`、冻结 evaluation protocol、real-store gate 和 EXP-APP 报告。
- 官方没有提供逐题答案、逐题分数或可下载 artifacts。本报告中的题型改进建议属于待验证假设，不是对私有题目的反向工程。
