# AML 开源榜分维度方案调研与 Mneme 下一轮研究建议

日期：2026-10-11

对象：Mneme 首轮 Full 结果（44.2543）及下一次 Full 的方法候选

## 结论

Mneme 当前最值得研究的不是扩大召回或引入 embedding/LLM，而是两个结构性缺口：

1. **B 关系与多跳**：让同一回答所需的多个 source、桥接 source 和关系路径在预算前缀中共同出现，并形成 Reader 容易使用的 evidence packet。
2. **E 个性化、D 的弱子类和 Streaming.online**：把偏好、身份和事实的更新表示为可追溯的状态演化，在当前状态问题中减少过期证据干扰，在历史问题中仍保留旧证据。

第一期领先开源方案提供了四条一致证据：

- 单纯的 **BM25 + dense + rank fusion** 已能显著改善 A/B，说明异构 cue 的覆盖比单一相似度更可靠。
- **原始 turn、role、timestamp 和局部交互上下文** 对 E 很重要；只保留压缩事实并不占优。
- 多跳领先方案都在做某种 **bridge completion**：先命中一个锚点，再沿实体、关系或新 query 找第二跳。
- 治理方向的有效机制是 **显式 update / valid-time / query-time evidence membership**，不是全局“越新越好”。

这些机制可以迁移成 Mneme 自身的无模型设计：保留统一 activation 主链，在 projection 前完成关系路径激活和状态有效性竞争，最终仍只返回带 provenance 的原始 spans。首选实验仍是已经有跨数据集证据的 `EXP-APP`；其后才是 activation 内的 bridge completion 和版本状态模型。

## 排名与数据边界

Mneme 的 44.2543 来自第二期完整评测，包含 Textual 和 Streaming，共 9,602 题。当前公开网页仍从第一期静态文件加载学术文本榜；第二期更多结果发布后，Mneme 的相对名次可能上升或下降。现在无法严谨地给出最终排名。

第一期公开学术榜有 50 个条目和 GitHub 地址，但静态结果中的 `target_git_sha` 全部为空。除仓库自己明确声明 tag/提交的项目外，不能假定仓库当前 `main` 就是当时受评实现。本报告把证据分成三档：

- **高置信**：仓库明确声明参赛版本，或者仓库最后提交早于提交日且实现与申报说明一致。
- **中置信**：架构和提交时间吻合，但官方静态数据没有固定 SHA。
- **研究参考**：仓库功能明显晚于第一期成绩，只能作为后续方法参考，不能用第一期分数证明其效果。

第一期和第二期的 suite、pipeline、Streaming 覆盖及聚合合同不同。以下分数只用于定位“哪些机制值得读”，不能用来计算 Mneme 的正式名次或预估下一次 Full 分数。

## Mneme 当前能力画像

| 能力 | Mneme 第二期 | 第一期公开最高 | 判断 |
| --- | ---: | ---: | --- |
| A 显式事实召回 | 50.02 | 63.47，MemMachine | 有提升空间，但不是最急 |
| B 关系与多跳 | **32.80** | 53.11，MemMachine | 明确短板 |
| C 时间与事件 | 41.03 | 37.92，MemMachine | 合同不同，至少不是一级主短板 |
| D 记忆治理 | 38.63 | 38.73，MemMachine | 总体不弱，内部 D1/D3 分化大 |
| E 个性化与关怀 | **31.88** | 58.32，M-flow | 明确短板 |
| G 上下文学习与执行 | 45.90 | 30.88，memfusion | 当前优势，应设保护门 |
| H 认识论安全与隐私 | 61.81 | 67.74，特殊化方案 | 当前优势，应设保护门 |
| Streaming.online | **36.73** | 第一期无同口径 | 高样本量主短板 |
| Streaming.intra_transfer | 97.92 | 第一期无同口径 | 很强，说明跨段保留不是问题 |

一级分数比对不能证明 Mneme 在 C/G/H 已经超过第一期系统，只说明下一轮不应对这些能力做大范围重写。Mneme 自身的低分且高样本量顺序仍是 `Streaming.online`、`B2`、`D1`、`C1`、`A3`；官方没有公开叶子 ID 的语义名称，因此本报告不擅自解释 B2、D1 等编号。

## 分维度领先方案

### B：关系与多跳

第一期 B 前五名：

| 系统 | B | 主要公开机制 | 版本归因 |
| --- | ---: | --- | --- |
| MemMachine | 53.11 | 多类记忆；当前版本有 query split / chain-of-query 迭代检索 | 当前实现晚于第一期，研究参考 |
| Mem0 | 49.01 | 原子事实、实体关联、混合召回、显式 ADD/UPDATE/DELETE/NONE | 官方静态结果无 SHA，中置信 |
| Hybrid Search v2.0 | 46.81 | BM25 + BGE-M3 dense，归一化分数融合，返回原始文本 | 2026-08-12 提交，较高置信 |
| InvMem | 45.96 | BM25 + dense 的 RRF；前 20 个种子补同会话 ±1 turn | 2026-08-11 冻结实现，较高置信 |
| Hybrid Episodic Memory | 45.90 | BM25 + dense RRF、原始 turn、局部 unit、Top-100 | README 声明 submitted configuration，高置信 |

这里最有价值的不是 dense 模型本身，而是三类检索行为：

1. **异构 cue 合取**：关键词擅长姓名、标题和精确值；语义通道补同义表达。Mneme 已有 lexical、frame、ontology、discourse 等结构 cue，关键是让它们形成互补覆盖，而不是再加 embedding。
2. **桥接检索**：MemMachine 当前 chain-of-query 会根据已找到证据继续追问缺失 hop；Mem0-BQE 只在首跳证据出现后生成一个 grounded bridge query，并最多替换最后一个结果；M-flow 从实体/原子断言沿图路径落到完整 Episode。
3. **局部上下文恢复**：InvMem 与 Hybrid Episodic 都把命中 turn 周围的交互内容带回，减少“答案在相邻 turn，但孤立 chunk 不自洽”的问题。

Mneme 不能直接复制“Top-K 后补邻居”或 LLM query expansion，因为这会绕开统一 activation field。对应的干净实现应是：

```text
query cues
  -> 初始 activation anchors
  -> 沿已经持久化的 proposition/entity/event/response 边传播
  -> 检查高强度路径是否缺少 bridge source
  -> 在同一 activation field 内守恒分配
  -> 全局排序
  -> Evidence projection / Top-K / token budget
```

所有 source 必须在 projection 前竞争；第二跳不能在 Top-K 后免费追加。研究指标应增加 `Complete@K`、bridge-source coverage 和 path compactness，而不只看单 source recall。

### E：个性化与关怀

第一期 E 前五名：

| 系统 | E | 主要公开机制 | 版本归因 |
| --- | ---: | --- | --- |
| M-flow | 58.32 | 原子 FacetPoint/Entity 锚点沿图落到完整 Episode bundle | 提交前仓库实现，中置信 |
| Raw Memory | 57.80 | 仓库当前 404，无法核验 | 不作机制推断 |
| Hybrid Episodic Memory | 57.29 | timestamp + role + 原始 turn；BM25/dense 双检索通道；RRF | 高置信 |
| ChronoHybridMem | 57.13 | 原始消息 + source-linked facts；FTS5/BM25；LLM 只排序已有 evidence ID | 官方 `v0.2.0`，高置信 |
| mem0-BQE | 56.89 | Mem0 原子偏好/事实 + 混合检索；grounded bridge query | 明确提交版本，高置信 |

E 的结果没有支持“压成用户画像就够了”。相反，成绩好的方案通常同时保留：

- 原始说法和 speaker；
- 时间与 source provenance；
- 原子偏好/身份视图；
- 相关交互或 Episode 的局部上下文；
- 多条相互关联的证据，而不是一条抽象 summary。

Hybrid Episodic 完全可以在没有 LLM extraction 的 raw 通道工作，且 E 达到 57.29。它说明偏好题的主要收益可能来自原始措辞、角色归属、时间和上下文完整性，而不一定来自更强模型。

Mneme 已经保留 raw span、role、timestamp、source_id，也有 typed proposition/frame。下一步不应再造一套 profile store；应检查这些结构在 100K 前缀中是否形成紧凑、可读、按 owner 聚合的 packet。`EXP-APP` 正好是最接近这一路径的现有候选。

### D 与 Streaming.online：更新、冲突和有效状态

第一期 D 前列包括 MemMachine 38.73、Raw Memory 38.04、ActiveMemoryIndex 37.95、TraceMem 36.34、Mem0 35.28。第一期 D 总分与 Mneme 第二期 D 总分接近，但 Mneme 的 D1 为 19.66、D4 为 81.60，说明不能用统一 recency boost 或统一压缩来改整个 D。

两类方案最值得区分：

1. **Mem0 的 destructive mutation**：新事实进入后，LLM 在 `ADD / UPDATE / DELETE / NONE` 中选择操作，并保留变更 history。优点是当前状态干净；风险是原始历史和旧状态容易在主检索面消失，影响历史、时间和认识论安全。
2. **ActiveMemoryIndex 的 membership-only 更新**：当前 Cycle-2 rc5 在 Add 时记录明确 replacement/correction，在 Search 时仅对当前状态问题暂时 withholding 被替代项；历史或时间问题保留旧证据。as-of 机制用有效时间范围选择 evidence，并用后续候选回填空位。它保持证据原文，不生成答案。

ActiveMemoryIndex 当前更新/as-of 实现晚于第一期 Full，不能用 37.95 的旧成绩证明这两个机制。但其公开配对实验报告了：显式更新集提升 65–70/400，as-of 集提升 30/300，同时 LoCoMo dated 和 knowledge-update guards 基本不退化。它是一个需要独立复现的研究线索。

Mneme 更适合 non-destructive state model：

- `Assertion` 永久保留 source provenance；
- 显式表示 `supersedes / retracts / confirms / contradicts`；
- 对可确定时间的状态保存 `valid_from / valid_to`；
- query activation 表示当前、历史或 as-of temporal scope；
- scope 参与 projection 前的 activation 竞争，不删除旧 source；
- 解析失败时保留全部候选，避免错误 suppression。

这可能同时改善 E、D1 和 Streaming.online。实现前必须先证明无模型 linguistic compiler 能以足够高精度识别明确 correction/replacement；如果精度不够，宁可只建可验证关系，也不要猜测更新。

### C：时间与事件

第一期 C 前三名是 MemMachine 37.92、M-flow 35.42、Mem0 26.83。M-flow 把细粒度断言、实体、Facet 和 Episode 组成图路径；Mem0 保留 mutation history；Hybrid Episodic 只有轻度 recency nudge，C 为 21.56。这个差异说明：

- 时间能力不等于给新消息加分；
- 事件顺序、状态版本、相对时间落点和 as-of validity 更重要；
- 只做全局 recency 会伤害旧事实与历史问题。

Mneme 的第二期 C=41.03 已经较强，且 API 已把 timestamp、role、source 写入 Reader 可见文本。因此 C 不适合单独做大改。应把时间工作放进上述 state model，并以 C 不退化作为硬门。

### A：显式事实召回

第一期 A 的领先方案是 MemMachine 63.47、M-flow 61.14、Mem0 58.72、Hybrid Search 57.87、Refind 57.75。Hybrid Search 的源码很简单：对同一用户所有原始记录重建 BM25，计算 BGE-M3 cosine，各自 min-max 后按 0.5 融合。它没有图推理、更新逻辑或 LLM，却同时取得 A57.87、B46.81。

InvMem 的更稳健版本使用 RRF 融合 BM25 和 dense，并补邻接 turn；其 A56.78、B45.96、总体 45.06。两者共同说明：精确字符串 cue 与语义/结构 cue 的互补很重要，融合标尺本身也会影响结果。

Mneme 不需要引入 dense 通道来复制这一结果。应审计 lexical、entity、predicate、role、event 等 cue 是否存在单一高 fan tag 垄断前缀，及多通道命中的 source 是否得到稳定而守恒的优势。`EXP-APP` 的 packet 组织和现有 source-peak 语义应先完成门禁，再决定是否需要新的 rank-space allocation。

### G/H：保护项

Mneme 的 G=45.90、H=61.81 是当前最强能力。第一期 M-flow 虽然 A/C/E/H 较高，但 G 只有 3.47；MemMachine 的 B/C/D 最强，但 G11.70、H30.32。这是重要反例：强图检索、摘要 bundle 或 agentic retrieval 可以改善部分维度，同时严重损害规则执行或证据边界。

下一候选必须保护：

- 程序、约束和指令的原始顺序；
- user/assistant/source 的明确归属；
- 旧事实与当前事实的 provenance；
- 不确定或没有证据时不伪造 state；
- 不把多个相似来源合并成看似独立的佐证。

任何事实改写、摘要替换、过期证据 suppression 或 Episode bundle 都必须经过 G/H proxy 的不退化门禁。

## 逐项目源码审计

### InvMem

审计提交：`31ab7bf9cfa3ee3c4f986e82f6e7a00b134ba8ca`，2026-08-11。

实际路径：

- Add 将原始消息切块，保留 role、timestamp、session；
- 默认 `BAAI/bge-small-en-v1.5`；
- Search 对 dense 和 BM25 排名做 RRF；
- 对前 20 个种子补同 session 的前后 1 条消息；
- 返回 Top-100 原始 evidence；
- README 报告 LoCoMo-Refined Evidence Recall@100 0.927652。

可迁移：多 cue rank fusion、局部上下文、原始 evidence。不可直接迁移：embedding 和 Top-K 后邻居追加。

### Hybrid Search v2.0

审计提交：`8ca665c4f697cc936b2326b5f42d9cf1756e2af3`，2026-08-12。

实际路径是 BM25 与 BGE-M3 dense 的 0.5 线性融合，两个 score 分别 min-max 归一化。它返回原始文本，没有更新、时间或关系层。它证明简单异构召回已经能拿到较强 A/B，但 min-max 对候选分布敏感，不适合直接成为 Mneme 的统一打分设计。

### Hybrid Episodic Memory

审计提交：`9db3399a7ccf8c1a46bcc3c204cdad20e8e8b6ba`，2026-08-07；仓库说明是 submitted configuration。

关键实现：

- raw channel：BM25 + `bge-small-en-v1.5` dense；
- 可选 extracted channel：Mem0 facts；
- weighted RRF，候选深度 400；
- timestamp 与 role 直接写进 evidence content；
- 连续同角色和过短消息合并，长消息按句边界分块；
- options 是独立 query channel，避免淹没主 query；
- 轻度 recency nudge；
- Top-100 原始证据。

E57.29 但 C21.56，说明 role/time/raw context 对个性化有效，而简单 recency 不能解决时间状态。

### ChronoHybridMem v0.2.0

审计 tag：`v0.2.0`，commit `7cf45c76ea7998554a13386b924627b83aeb3134`。

Add 同时保存原始消息和 `gpt-4o-mini` 提取的 source-linked facts；两者进入 SQLite FTS5。Search 用 FTS5/BM25 找候选，再让 `gpt-4o-mini` 只返回已有 evidence ID 的顺序。系统不生成答案。

它的 E57.13、B44.44，但 C23.30。可迁移的是 raw + structured 双视图、严格 source linkage 和“只排序已有证据”的边界；Mneme 已具备这三点，无需复制 LLM fact extraction/reranking。

### M-flow

审计提交：`0d585cda2f588af69fb872ae6914caba0c217816`，2026-08-03。

它把 Entity、FacetPoint、Facet、Episode 组成倒锥形图：query 在多个粒度找到 anchor，沿带语义的边向 Episode 传播 path cost，以最短的一条强路径决定 Episode 分数，最后返回完整 bundle。实体可桥接不同文档。

可迁移的是“精细 anchor → grounded path → coherent landing packet”和“一条强路径足以建立相关性”。不可迁移的是向量化节点/边、summary bundle 和当前自适应权重。其 G3.47 也说明完整 bundle 容易带入大量与规则执行无关的上下文。

### Mem0 与 Mem0-BQE

Mem0 的稳定核心模式是先提取原子 facts/preferences，再检索相关旧记忆，由 LLM 决定 `ADD / UPDATE / DELETE / NONE`，并记录 mutation history。公开版本还支持 dense、BM25、entity boost 和 reranker。

Mem0-BQE 明确冻结为 `v1.1-20260807`，仓库 commit `a1b1debf8d6b219826dff5a0934c06a046872882`。它先运行 Mem0 原生混合检索，再让 `gpt-4o-mini` 从前五条证据中抽一个必须逐字出现的 bridge entity，执行一次额外 Search，最多把一个新 memory 放到最后一位。任何失败都返回原排序。

BQE 是很干净的 bridge-completion 对照，但仍有两个限制：首跳必须进入前五；同名实体会引入错误第二跳。Mneme 若做对应机制，应直接利用 typed entity/relation provenance，避免生成 query 和字符串同名歧义。

### ActiveMemoryIndex

第一期公开成绩没有固定 SHA；当前审计提交 `7a6e152340a784883e241dd37e6ef399b21a4be8` 是 2026-10-07 的 Cycle-2 rc5，README 明确写着 Full 尚未启动，因此不能把当前 explicit-update/as-of 功能归因于第一期分数。

当前代码仍值得作为后续研究参考：原始 timestamped turns 与 atomic first-person facts 双存；raw-first ordering；邻居窗口；Top-100；明确 replacement/correction 的 precision-first 记录；历史问题保护；as-of interval membership；任何模型失败都“withhold nothing”。其可迁移价值是状态与 evidence membership 的语义，而不是其 LLM detector、query router 或语言规则。

### MemMachine

第一期 B/C/D 均第一。当前仓库提交为 2026-10-09，晚于第一期，不能把当前 retrieval agent 直接解释为旧成绩原因。当前实现的 ChainOfQuery 会判断现有 evidence 是否足够，并针对最早缺失 hop 继续检索，最多三轮；另有 graph episodic memory、SQL profile memory 和 working memory。

它给 Mneme 的研究线索是“证据充分性”和“缺失 bridge 定位”，不是照搬 LLM agent、英文 query regex 或多存储路由。

## Mneme 下一轮候选顺序

### P0：固定可复现基线

第二次 Full 前冻结：

- `mnemekit==0.8.3`；
- `mneme-api` 固定 commit；
- 默认 `TAG_GRAPH_DEDUP`；
- Top-K 100；
- `o200k_base`、100K EvidenceBudget 和当前 formatter；
- schema 3；
- Add/Search 并发与部署资源。

当前 API 仓库已经 pin 到 0.8.3，实际功能升级提交是 `e8b2e90`，其后的相关提交仅增加运行报告。正式公开条目应提交一个固定 commit/tag，并说明核心包的 PyPI 版本、Git tag 和核心 commit。首轮 Full 中途升级过核心版本，因此申请公开时应如实说明，并让官方确认结果最终关联的版本标签；下一轮从 Add 到 Eval 必须保持单一版本。

### P1：完成 `EXP-APP` 晋级门禁

这是现有证据最充分、改动最小的质量候选：不加模型、embedding、题型路由或后检索扩展，只重组 graph-reachable tail，使相关 source 在预算内形成更紧凑 packet。

晋级条件：

- LoCoMo、LME-S、BEAM 的 8K/24K/100K source Recall/Any/Complete 不退化；
- B proxy 的 Complete@K、bridge coverage、path compactness 提升；
- Qwen3.6 Reader / MiniMax-M3 Judge 三次配对结果稳定；
- G/H proxy 与 C 不退化；
- 线上级 1,112-history Store 的 latency/RSS 可接受。

### P2：activation 内的 bridge completion

目标是借鉴 MemMachine、M-flow、BQE 的共同点，但遵守 Mneme 设计锁：

- 初始 cue 激活 source/frames；
- 检测已激活关系路径中尚未获得独立 source 支持的 bridge；
- 只沿已持久化 typed relation、entity、event、response provenance 传播；
- activation 守恒；
- 全部候选在 projection 前统一竞争；
- 禁止 Top-K 后追加，禁止 query 类型规则。

先做 reader-free 消融。若只是改变大量排序却不提高 Complete@K，不进入 Reader/Judge。

### P3：non-destructive revision state

先构造公开、通用的增量更新诊断集：明确 replacement、correction、retraction、confirmation、历史查询、当前状态、as-of、同名主体和否定。每次 Add 后立即 Search。

先测 formation 能否从统一 linguistic compiler 高精度产生 revision edges；再测 temporal-scope activation。主要指标：

- add-to-search visibility；
- current-state precision；
- historical evidence retention；
- obsolete evidence suppression precision/recall；
- Evidence digest 随 Add 的演化；
- LoCoMo/LME/BEAM 和 G/H guard 不退化。

这一路如果成功，最可能同时改善 Streaming.online、E 和 D1；也最容易因错误 suppression 伤害 H，所以应晚于 `EXP-APP`。

### P4：再研究 channel allocation

若 P1/P2 后 A3 仍弱，再检查多 cue 汇聚与高 fan tag 竞争。对照实验可使用 RRF 的思想，但实现必须属于统一 activation field，不能在 evidence 生成后另做第二套 ranker。

## 不建议采用的方向

- 不因第一期领先方案普遍用 embedding 就给 Mneme 加 embedding。它会削弱核心贡献，也没有证明是 B/E 的必要条件。
- 不加 Search-time LLM query expansion 或 LLM reranker。BQE/ChainOfQuery 可作为机制启发，Mneme 应以 grounded graph 完成同类工作。
- 不做全局 recency boost。它不能处理 as-of/history，还会伤害旧事实。
- 不把旧事实 destructive update 掉。保留 immutable source 和 revision graph。
- 不在 Top-K 后补 turn、邻居或 Episode；任何上下文都必须在 projection 前计入 item/token 成本。
- 不按 B2、D1、E3 等未知私有标签写规则。
- 不根据 options 生成或排序答案；Mneme 的方法改进应对开放题和选择题统一成立。
- 不把当前仓库的赛后功能错误归因于第一期榜单成绩。

## 对核心实现方的直接建议

先把 `EXP-APP` 做成一个可复现候选，并新增多证据联合覆盖指标。它最符合现有架构，也最直接回应 B/E 的证据组织问题。

随后只开两条独立研究分支：

1. **grounded bridge completion**：在统一 activation 中补齐关系路径；
2. **revision-state activation**：以不可变 provenance 表示状态版本和时间有效性。

不要把两者一次性合并。每条分支都应相对冻结 0.8.3/`EXP-APP` 做严格 source sequence、Evidence digest、Reader/Judge 和保护维度配对。只有跨 LoCoMo、LME-S、BEAM 和增量更新集都成立的通用机制，才进入第二次 Full。

## 来源

- AML 官方仓库与能力定义：https://github.com/AML-memory/agent-memory-leaderboard/tree/1b8142bfe0f20f1c5218d6b554aa0012de34e504
- 第一期学术文本榜静态结果：https://agentmemoryleaderboard.ai/static/cycle1-academic-textual.json?v=pages-migration-20260919
- InvMem：https://github.com/wenxiaof345-ctrl/vanilla-rag-memory/tree/31ab7bf9cfa3ee3c4f986e82f6e7a00b134ba8ca
- Hybrid Search：https://github.com/cydd-1972/hybrid_search/tree/8ca665c4f697cc936b2326b5f42d9cf1756e2af3
- Hybrid Episodic Memory：https://github.com/tlysanhuo/agent-memory-challenge/tree/9db3399a7ccf8c1a46bcc3c204cdad20e8e8b6ba
- ChronoHybridMem v0.2.0：https://github.com/Tin11Mn/chrono-hybrid-mem/tree/v0.2.0
- M-flow retrieval architecture：https://github.com/FlowElement-xinliuyuansu/m_flow/blob/0d585cda2f588af69fb872ae6914caba0c217816/docs/RETRIEVAL_ARCHITECTURE.md
- Mem0：https://github.com/mem0ai/mem0
- Mem0-BQE：https://github.com/Cyrus580529/mem0-agent-memory-challenge/tree/a1b1debf8d6b219826dff5a0934c06a046872882
- ActiveMemoryIndex rc5：https://github.com/linxuhao/ActiveMemoryIndex/tree/7a6e152340a784883e241dd37e6ef399b21a4be8
- MemMachine：https://github.com/MemMachine/MemMachine

本报告没有使用官方私有题目、gold、逐题答案或评测 artifact。第一期分数来自官网公开静态学术文本榜；Mneme 分数来自其已完成的第二期私有结果。跨期对比仅作研究导航。
