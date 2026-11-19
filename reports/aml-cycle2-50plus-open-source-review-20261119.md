# AML 第二期开源榜 50 分以上方案复盘与 Mneme 下一期路线建议

日期：2026-11-19  
对象：Mneme 核心实现方  
性质：公开榜单与开源实现研究；不包含官方私有题目、答案或逐题评测数据

## 结论

第二期 Textual Open-source Methods 榜共有 89 个提交，其中 **82 个达到 50 分**。
Mneme 正式成绩为 **56.62，排名 51 / 89**。

最重要的结论不是“头部都用了 embedding，所以 Mneme 也必须用”，而是：

1. 已确认至少 9 个 50 分以上提交在正式参赛路径中不使用稠密 embedding、生成式 LLM
   或 learned reranker；其中 LexiRecall 只用 BM25、原文、时间注释和可选邻域，就取得
   **58.08、排名 35**，比 Mneme 高 **1.46pp**。
2. 因此，embedding 不是参加下一期或超过当前 Mneme 的必要条件。当前证据支持先保留
   Mneme 的 zero-embedding / zero-generative-LLM / zero-learned-reranker 区分度。
3. 头部系统普遍使用 dense + lexical，但它们同时也做了证据预算、邻域补全、相对日期、
   session 聚合、覆盖与冗余控制。排行榜不能把这些收益与 embedding 收益拆开，不能把
   头部相关性写成 embedding 的因果收益。
4. 下一期最值得优先验证的是：多视角词法融合、同会话结构补全、确定性相对日期展开、
   evidence coverage/diversity、紧凑预算，以及 Streaming feedback 与普通事实的隔离。
5. Mneme5 directional successor recall 已在正式 Full 中带来 +6.50pp 综合收益，必须保留。
   新实验只能研究它的适用域、预算和 route precision，不能因局部回退直接移除。
6. embedding 只应作为最后的 necessity control。只有在固定评测、多个预算和关键切片中
   稳定带来至少 **2pp 绝对提升**，且不破坏 H、G、Streaming，才值得重新讨论是否牺牲
   Mneme 当前的产品和论文声明。

## 研究范围与证据边界

本次以官方 Cycle 2 Textual Open-source Methods 页面为榜单口径，记录 50 分以上全部
82 个系统的官方名次、分数、版本和公开仓库。

审计分三层：

| 层级 | 范围 | 能支持的结论 |
| --- | --- | --- |
| 榜单级 | 全部 82 个 50+ 提交 | 名次、分数、公开仓库、版本 |
| README/配置级 | 全部 82 个公开仓库 | 作者公开声明的主要组件和运行方式 |
| 源码级 | 头部代表方案及疑似 zero-embedding 方案 | 正式/冻结参赛路径是否实际调用 embedding、LLM、reranker，以及关键检索机制 |

未逐一源码验证的系统只用于观察方法分布，不据此声称其精确组件或单项因果收益。
仓库中存在 embedding 模块也不自动代表正式提交使用了 embedding；反过来，README
未出现 embedding 字样也不自动代表正式路径是零模型。因此 zero-embedding 清单只纳入
已能从冻结版本、部署配置或参赛 server 路径确认的系统。

## 官方结果快照

Mneme 的正式公开指标为：

| Overall | A | B | C | D | E | G | H | Streaming |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 56.62 | 60.42 | 52.27 | 54.82 | 65.79 | 34.21 | 54.44 | 63.66 | 43.76 |

榜首 Resurface 为 61.22。已确认的 zero-dense 最高分 LexiRecall 为 58.08，与榜首相差
3.14pp，与 Mneme 相差 1.46pp。这个区间说明纯词法路线仍有明确可挖空间，但不能证明
58 分是纯词法方法的硬上限。

## 已确认的零稠密 embedding 方案

这里的“零稠密 embedding”指参赛 Add/Search memory path 不使用神经语义向量；BM25、
FTS5、TF-IDF、词干和字符 n-gram 属于确定性稀疏词法表示。表中系统同时不使用生成式
LLM 或 learned reranker，除非另有说明。

| 排名 | 系统 | 分数 | 已确认的主要机制 |
| ---: | --- | ---: | --- |
| 35 | LexiRecall | **58.08** | 用户内 BM25、320-token 分块、options 拼接、原文、相对日期注释、可选同会话邻域 |
| 49 | ChronoMem | 56.92 | BM25、1600 字符分块/200 重叠、稀有 query 词选择、中英词项、时间戳 |
| 51 | Mneme | 56.62 | Mneme5 successor/revision、spaCy 语言结构、原始 evidence、100K token budget |
| 52 | agent-memory | 56.56 | FTS5 + word/CJK BM25 + options + session-window + code-symbol 多路 RRF、相对日期、邻域 |
| 55 | AML 时序证据记忆系统 | 56.04 | FTS5、中文 2/3-gram、精确 clue、RRF、覆盖选择、冗余惩罚、时间方向、24K 字符预算 |
| 57 | iHow Memory AML Textual | 55.87 | 用户内 BM25、原始消息、同会话 ±1 邻居、role/timestamp 保真 |
| 58 | EvidenceMemory | 55.58 | 原词与词干 BM25、speaker/session 结构、cross-chunk continuity、parent block、词法 RRF |
| 75 | AILIS Memory | 51.42 | BM25、短语和数字 boost、轻量 recency/importance、session repeat penalty |
| 80 | EverMind | 50.39 | TF-IDF cosine + BM25 + freshness；无需预训练模型、GPU 或外部服务 |

### 与 Mneme 的维度对比

| 系统 | Overall | A | B | C | D | E | G | H | S |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LexiRecall | **58.08** | 61.09 | 53.38 | 57.74 | 68.30 | 38.78 | 57.76 | 65.32 | 44.35 |
| ChronoMem | 56.92 | 60.29 | 50.98 | 56.15 | 65.38 | 37.64 | 55.88 | 61.97 | 47.22 |
| **Mneme** | **56.62** | **60.42** | **52.27** | **54.82** | **65.79** | **34.21** | **54.44** | **63.66** | **43.76** |
| agent-memory | 56.56 | 61.30 | 50.90 | 55.04 | 60.37 | 41.80 | 57.61 | 62.65 | **49.26** |
| AML 时序证据记忆 | 56.04 | 60.35 | 48.16 | 56.50 | 63.42 | **42.46** | 54.77 | 65.78 | 44.42 |
| iHow Memory | 55.87 | 58.78 | 52.80 | 54.92 | 64.78 | 36.48 | 55.73 | **68.70** | 44.64 |
| EvidenceMemory | 55.58 | 58.17 | 52.43 | 54.30 | 64.81 | 37.91 | 56.02 | 67.08 | 44.69 |

这些是不同完整系统之间的横向相关性，不是 paired ablation。可以用来选择实验方向，
不能把某个高分维度直接归因给某个单一组件。

## 关键方案源码观察

### LexiRecall：最重要的零模型参照

LexiRecall 的核心路径非常简单：

1. Add 保留原始消息、role、session 和 timestamp；按固定 token 数分块。
2. Search 在当前 user 的全部文本上计算 BM25。
3. options 可作为附加词法查询，但没有 query LLM。
4. 对文本中的 yesterday、tomorrow、today 等相对日期，按 source timestamp 生成绝对日期
   注释；不改写原文。
5. 支持同 session 邻域窗口，但默认配置和最终部署参数仍应以冻结环境为准。

它的意义不是“BM25 已经足够解决所有记忆问题”，而是证明了简单、忠实、Reader-friendly
的 evidence pipeline 本身可以达到 58.08。Mneme 不能默认把更多内部结构和 100K evidence
当作优势；这些结构必须证明最终提高了 Reader 可用证据密度。

### agent-memory：多视角词法融合的直接参照

正式 competition server 使用多个确定性 channel：

- SQLite FTS5 BM25；
- 自定义 word/CJK BM25；
- 四消息、步长二的 session sliding window BM25；
- options 独立通道，避免选项淹没主 query；
- code-symbol 精确通道；
- 相对日期注释；
- 最后用 RRF 融合，并补同会话邻居。

其整体只比 Mneme 低 0.06pp，但 E、G、Streaming 分别高 7.59、3.17、5.50pp。虽然不能
直接归因，多路词法和 session continuity 是 Mneme 下一期最值得做的低风险对照。

### AML 时序证据记忆：规则版 coverage selection

该方案中的 `hybrid` 指多路词法，不是 dense vector：

- jieba/Latin tokens；
- 中文字符 2/3-gram；
- 名称、数字、日期 exact clue；
- FTS5/BM25；
- RRF；
- greedy feature coverage；
- redundancy penalty；
- 明确 before/after/since/earliest/current 时才启用时间方向；
- direct evidence 入选后才补同会话 context；
- 24K 字符总预算。

这套设计可视为不依赖模型的轻量 MemPursuit：不是继续扩大候选集合，而是在固定预算中
提高不同 query clue 的覆盖率，并减少重复 evidence。

### ChronoMem、iHow 与 EvidenceMemory：简单结构仍有价值

- ChronoMem 对长 query 只保留已知词项中最稀有的 32 个，避免通用词稀释 BM25；其
  Streaming 47.22，值得做 query-term selection 对照。
- iHow 用原始消息作为基本单元，只做 BM25、rank score 和同会话 ±1 邻居；不做摘要，
  保留“谁在什么时候说了什么”。
- EvidenceMemory 用 intact token、stem token、speaker/session continuity 和 parent-block
  return 补足单个 chunk 不完整的问题。

### AILIS 与 EverMind：不建议作为主线，但可保留局部机制

AILIS 的 BM25 phrase/numeric boost 和 soft session diversity 很轻量，但 Overall 51.42、
B 39.56、D 42.44，说明简单 recency/importance/session penalty 本身不足以处理 revision 和
multi-hop。EverMind 的 TF-IDF + BM25 是无神经模型基线，但成绩 50.39，也没有显示出比
Mneme 当前结构更强的整体价值。

## 头部系统中与 embedding 无关的可借鉴机制

### Resurface，排名 1，61.22

- FTS5 BM25 + text-embedding-v4 dense 两路；
- 等权 RRF，`k=60`；
- 不使用 learned reranker；
- 返回原始 evidence；
- 对命中 turn 补 ±1 邻居。

可借鉴的是简单、稳定的 rank fusion 与邻域；dense route 暂不进入 Mneme 主线。

### mnemotree，排名 2，60.81

- FTS5 BM25 + sqlite-vec exact dense；
- RRF，无 reranker、LLM 或 extractor；
- 8K token evidence budget；
- 每个 source 先保留一个 anchor chunk；
- 同 session ±1 邻居并合并连续 block；
- 相对日期注释；
- assistant 文本占比达到阈值时才拆 user/assistant 分区。

对 Mneme 最重要的是 8K 紧凑 evidence、source-level allocation 和连续 block packing。

### starwingMem，排名 3，60.56

- dense、sparse、BM25 三路加权 RRF；
- session-level RRF；
- 16K token budget；
- 时间范围 boost、future penalty、相对日期注释；
- preference/advice 原文 quote 辅助；
- 将 `Streaming online QA feedback:` 排除出普通索引。

仓库报告的本地 ablation 中，自然日期注释对 LoCoMo 提高约 2.4pp；索引 Streaming
feedback 使 LoCoMo 降低约 3.8pp；32K/64K 相对 16K 没有显著收益。它们不是官方 paired
ablation，但足以支持 Mneme 优先测试日期、feedback isolation 和 evidence budget。

### PaiMem 与 RAW-RAG

PaiMem 使用 dense + BM25、4B MemReranker 和 residual/complementarity evidence selection；
RAW-RAG 使用 dense Top-128、Cohere rerank 后只保留最多 15 个 chunk。二者说明紧凑选择
可能重要，但 learned reranker 与外部模型不应直接进入 Mneme 下一期主方案。

### Mneme-Asterion、MemLink、MemMachine 等复杂路线

这组系统加入 LLM extraction、search-time planning、图结构、摘要、冲突状态或 vector graph。
它们有可研究价值，但没有形成“复杂度越高、官方分数越高”的稳定关系。下一期不应优先
复制这些系统，以免同时失去确定性、低成本和 zero-model 声明。

## 82 个 50+ 方案呈现的方法格局

公开实现大体落入四个重叠家族：

1. **dense + lexical + RRF**：50+ 榜单的主流，尤其集中在头部；通常还包含时间、邻域和
   evidence packing。
2. **dense candidate + learned reranker**：上限较高但成本、延迟和外部依赖显著增加，公开
   结果也没有证明 reranker 必然优于简单 RRF。
3. **LLM extraction / summary / state / graph**：试图解决更新、偏好和多跳，但实现复杂，
   结果方差较大。
4. **lexical / rule / structural evidence**：数量较少，但已经覆盖 50.39--58.08，并证明
   zero-dense 路线仍具竞争力。

跨家族反复出现、且不要求 embedding 的组件是：

- 原始 evidence 与 provenance 保真；
- BM25/FTS5；
- 同会话邻域或 turn completion；
- 相对日期绝对化；
- query temporal scope；
- source/session 聚合；
- RRF；
- 固定 evidence budget；
- coverage/diversity 与 redundancy penalty；
- Streaming feedback 隔离；
- options 与主 query 分通道处理。

这组交集比“换一个 embedding 模型”更适合作为 Mneme 下一期第一阶段路线。

## Mneme 下一期建议架构

保持现有 Add/Search memory path 的声明不变：

```text
zero dense embedding
zero generative LLM
zero learned reranker
deterministic lexical + linguistic + temporal + provenance-aware evidence retrieval
```

建议在 Mneme5 周围增加五个可独立开关的组件：

```text
query
  -> deterministic query views
       - word / lemma / stem
       - CJK char n-gram
       - exact name / number / date / symbol
       - options channel
       - temporal scope
  -> existing Mneme activation + Mneme5 successor route
  -> per-view ranks
  -> rank fusion
  -> source/session coverage selection
  -> direct-evidence-gated neighbour completion
  -> fixed token-budget packing
  -> original evidence + provenance
```

不要把多路词法实现成另一个不透明“大 ranker”。每个 view 必须能单独记录候选、命中、
rank contribution 和最终被选择/拒绝原因，以便分层归因。

## 分阶段实验与准入门禁

所有阶段使用同一冻结 baseline、固定样本、相同 Reader/Judge 和相同随机种子。上游未
通过时不得进入下游或把多个未经验证的改动一起提交 Full。

### Stage 0：冻结基线与审计集

要回答：当前 Mneme5 在不同预算、数据集和能力切片上的稳定基线是什么。  
不回答：任何新机制是否有效。

输入为当前 Mneme5；输出总体与 A/B/C/D/E/G/H/Streaming proxy、evidence token 数、
source/session 数、重复率、无证据率，以及随机/正向/反向/边界 case 审计。

准入条件：同配置重复运行结果稳定；指标、预算和 evidence hash 可复现。否则 `hold`。

### Stage 1：evidence budget 与 packing

固定检索语义不变，只比较 8K、16K、24K、48K、100K token。增加每 source anchor、连续
block 合并与重复 source 抑制，但不得改变候选相关性逻辑。

主指标：总体、H、C、Streaming、Reader-visible gold/source coverage。  
失败指标：关键 source 被系统性截断、H 下降、延迟或 payload 失控。

只有至少一个紧凑预算在总体不退化、关键切片无实质下降，并显著降低 token/重复率时
`pass`。否则保持现有 100K，不得仅因头部系统使用 8K/16K 就切换。

### Stage 2：多视角词法融合

在相同 evidence budget 下依次加入：lemma/stem、char n-gram、exact clue、options 独立通道、
RRF。每次只增加一个 view，并与当前 Mneme activation 做 paired comparison。

主指标：A、B、G 和总体；同时检查 query language、实体/数字/日期、长短 query 分层。  
失败指标：generic token 引入大量噪声、options 污染事实、延迟超限、H/C 回退。

未经独立评测的组合只能叫 `candidate`，不能叫 validated successor。

### Stage 3：时间方向与相对日期

先只做 source timestamp 驱动的确定性相对日期注释，再单独测试 before/after/since/current/
earliest 等明确 temporal scope。没有明确方向时不得默认最新优先。

主指标：C、D、Mneme5 revision case；失败指标：future leakage、原始 timestamp 未知时臆造、
C2/H 回退。

### Stage 4：邻域、coverage 与 diversity

先命中 direct evidence，再允许同 session ±1、完整 turn 或小型滑窗竞争剩余预算。随后测试
query-clue coverage、session/source redundancy penalty、role-aware allocation。

主指标：B、E、G、Streaming 和 multi-evidence completeness。  
失败指标：邻域挤掉 direct evidence、assistant 建议冒充用户事实、重复 session 占满预算。

### Stage 5：Streaming feedback isolation

区分原始用户事实、assistant 建议、评测/反馈文本、revision/successor。先只做类型隔离和
可观测性，再测试不同类型的 route 与预算，不按 benchmark 名称做规则。

主指标：Streaming.online、Streaming.intra_transfer、G、H。  
失败指标：在线反馈进入长期事实、revision 被错误屏蔽、旧事实无法被 successor 恢复。

## Embedding necessity gate

只有 Stage 1--5 的 zero-dense 路线完成并出现可复现平台期后，才允许建立 embedding
诊断分支。该分支不替代主线，也不直接成为下一期提交。

固定三组对照：

1. 当前 zero-dense 最优候选；
2. 只增加 dense candidate channel，保持相同最终预算和 packing；
3. dense + lexical RRF，但不增加 reranker、LLM 或免费邻域。

只有同时满足以下条件才可提出合并建议：

- 多个预算和重复实验方向一致；
- 总体绝对提升至少 2pp；
- 主要增益可定位到词法确实召回不到的 paraphrase/semantic case；
- H、G、Streaming 无实质回退；
- Add/Search 成本、延迟、可复现性和隐私边界可接受；
- 完整说明失去 zero-embedding 声明的产品与论文代价。

若不满足，结论应为“embedding 在当前边界内没有证明必要”，而不是继续换模型、扩大
候选或增加 reranker 来绕过失败门禁。

## 建议的实施优先级

| 优先级 | 实验 | 原因 |
| --- | --- | --- |
| P0 | 8K--100K budget sweep + evidence density audit | 头部普遍更紧凑，且 Mneme H/C/Streaming 有噪声风险 |
| P0 | 相对日期确定性注释 | 多个高分方案重复出现，简单、可解释、零模型 |
| P0 | 同 session direct-hit-gated ±1 邻域 | agent-memory/ChronoMem/iHow 的 Streaming 提供方向性证据 |
| P1 | lemma/stem + CJK n-gram + exact clue 多路 RRF | 直接吸收 zero-dense 组最稳定的共同结构 |
| P1 | coverage/diversity 与 redundancy penalty | 提高固定预算中的证据互补性 |
| P1 | options 独立低权重通道 | 避免拼接 options 淹没主 query |
| P1 | Streaming feedback 类型隔离 | starwingMem 本地 ablation 与 Mneme Streaming 结果共同指向该风险 |
| P2 | session-level/window retrieval | 潜在收益高，但需控制长上下文与重复 evidence |
| 最后 | dense embedding necessity control | 只有 zero-dense 路线平台期后才有解释价值 |

## 交付判断

当前建议为 **pass：进入下一期 zero-dense 候选研究**，但不是直接提交新版本。

- 保留 Mneme5 和现有正式 baseline；
- 先完成 Stage 0 固定评测；
- 按 P0 顺序逐项做 paired ablation；
- 任一阶段 `hold/fail` 不进入下游；
- 未经固定评测验收的输出统一命名为 `candidate` 或 `pilot`；
- 不因头部排名直接加入 embedding。

## 附录：官方 50 分以上提交

以下只记录官方名次、系统和 Overall，方法归因仍以上文证据边界为准。

| 排名 | 系统 | Overall | 排名 | 系统 | Overall |
| ---: | --- | ---: | ---: | --- | ---: |
| 1 | Resurface | 61.22 | 42 | WeftMem | 57.67 |
| 2 | mnemotree | 60.81 | 43 | theSamael | 57.33 |
| 3 | starwingMem | 60.56 | 44 | ActiveMemoryIndex | 57.26 |
| 4 | PaiMem | 60.41 | 45 | apple | 57.13 |
| 5 | RAW-RAG-AML | 60.38 | 46 | Tiger memory | 57.02 |
| 6 | uuyz-aml-memory | 60.35 | 47 | MemMachine | 57.00 |
| 7 | 赏金猎人 | 60.26 | 48 | Nagasaki soyo's memory | 56.94 |
| 8 | Cordmem | 60.12 | 49 | ChronoMem | 56.92 |
| 9 | LMC-5 | 59.97 | 50 | memorysum | 56.78 |
| 10 | plain-memory | 59.95 | 51 | Mneme | 56.62 |
| 11 | khipu | 59.83 | 52 | agent-memory | 56.56 |
| 12 | deja-vu | 59.82 | 53 | 和光证据记忆 | 56.44 |
| 13 | E2-Mem | 59.77 | 54 | MantaRecall | 56.34 |
| 14 | MemTrace | 59.72 | 55 | AML 时序证据记忆系统 | 56.04 |
| 15 | GeeMem | 59.63 | 56 | Mem-3-to-1 | 55.94 |
| 16 | Verbatim Harbor | 59.56 | 57 | iHow Memory AML Textual | 55.87 |
| 17 | TianxiMemory | 59.47 | 58 | EvidenceMemory | 55.58 |
| 18 | CueTrail | 59.45 | 59 | Agent0Mem | 55.45 |
| 19 | Mneme-Asterion | 59.42 | 60 | jiuwen-memory | 54.88 |
| 20 | VAULT | 59.36 | 61 | RRF Fusion with ReRanker | 54.87 |
| 21 | Mandol | 59.26 | 62 | StreamICL | 54.84 |
| 22 | RE-call | 59.11 | 63 | Retrace | 54.83 |
| 23 | Zhiji Witness Memory | 59.08 | 64 | Star-Atlas-Memory-Text | 54.50 |
| 24 | agentmem | 59.05 | 65 | LCM-X | 54.49 |
| 25 | GapTrail Memory | 59.02 | 66 | aml-memory-adapter | 54.35 |
| 26 | ASMEM | 58.82 | 67 | MemCore | 53.89 |
| 27 | Tidemark | 58.75 | 68 | Ariadne | 53.83 |
| 28 | ReMemer | 58.53 | 69 | Chronicle Memory / ForageTrace | 53.78 |
| 29 | GraphMemory | 58.52 | 70 | memory-as-history | 53.40 |
| 30 | EviWeave | 58.48 | 71 | FactTrace | 53.17 |
| 30 | UserTrail Memory | 58.48 | 72 | Memprism | 53.00 |
| 32 | MemLink | 58.22 | 73 | musemem | 52.97 |
| 33 | MemCharter | 58.21 | 74 | Z memory | 52.29 |
| 34 | Dandelion Memory | 58.19 | 75 | AILIS Memory | 51.42 |
| 35 | LexiRecall | 58.08 | 76 | AM-Link | 51.35 |
| 36 | MemMoring-Rag | 58.07 | 77 | libmem | 51.04 |
| 37 | evidence-rank-memory | 58.00 | 78 | Aranea-Agents Memory | 50.94 |
| 38 | miyako_viola | 57.94 | 79 | SYUNE | 50.82 |
| 39 | ChronoTrace Memory | 57.90 | 80 | EverMind | 50.39 |
| 40 | SourceTrail | 57.82 | 81 | AxiomMem | 50.36 |
| 40 | opencontext | 57.82 | 82 | 我的记忆系统 | 50.19 |

## 公开来源

- 官方 Cycle 2 Textual Open-source Methods：
  <https://agentmemoryleaderboard.ai/leaderboard/academic/textual>
- LexiRecall：<https://github.com/lyzhaha/LexiRecall-pub>
- ChronoMem：<https://github.com/a1750235782-a11y/chronomem>
- agent-memory competition server：<https://github.com/dorianherle/agent_memory>
- AML 时序证据记忆：<https://github.com/renzhaochao/aml-starter-template>
- iHow Memory：<https://github.com/iHow1/ihow-memory-aml-textual>
- EvidenceMemory：<https://github.com/X3NNY/evidence-memory>
- AILIS Memory：<https://github.com/haowenGuo/ailis-agent-memory-challenge>
- EverMind：<https://github.com/liuyingtie/aml-memory-adapter>
- Resurface：<https://github.com/lilysttail/aml-textual-memory>
- mnemotree：<https://github.com/kurcontko/mnemotree>
- starwingMem：<https://github.com/seuclkzsd/starwingMem>
- PaiMem：<https://github.com/vikotse/PaiMem>
- RAW-RAG：<https://github.com/Caspian-Li/raw-rag-aml>
- Mneme-Asterion：<https://github.com/Supan-Silas/Mneme-Asterion>

