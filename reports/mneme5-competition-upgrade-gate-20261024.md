# Mneme5 候选用于 AML 第二次 Full 的升级标准

日期：2026-10-24\
当前生产候选：`mnemekit==0.10.1`\
评审对象：`EXP-DDR` / forward successor activation / 完整 persistent revision\
结论状态：Mneme5 论文研究门 PASS；API/真实性能 PASS；比赛冻结回放 PASS；待官方 Smoke

最新审查点：核心方法 commit `76715e6`，论文证据 commit `4fd74cf`，正式发布 commit
`2c69a58` / tag `v0.10.0` / `mnemekit==0.10.0`。2026-10-24 在发布线复核核心测试为
`360 passed, 4 subtests passed`；PyPI 回装后的 API 契约测试为 `7 passed`。

`mnemekit==0.10.0` 的 NO-GO 结论保留为历史记录。2026-10-29 的安全修订版 0.10.1 已在
不读取 benchmark 名称、question ID、operation label、answer 或 gold evidence 的前提下，
通过同一冻结回放：STALE sealed 结果逐字节保持；MemOps 三轮 Accuracy 均不下降；
LongMemEval-S 三轮平均 Accuracy `+0.267pp`、Token-F1 `+0.498pp`。因此 0.10.1 可进入
第二次 AML Full 的官方 Smoke 与最终部署流程。

## 0.8 最终安全修订与放行结论（2026-10-29）

### 机制冻结

0.10.1 不改变 relation 构建、阈值、margin、activation、持久化格式或 Add 行为，只约束
query-time admission 与 evidence order：

- successor seed 只来自原 activation 的前 40 个 source，仍最多覆盖 10 个 event；
- 单一 owner 的 source-atomic episode 保留 0.10.0 的 score-ranked successor activation；
- 同一 packet 同时包含 user/assistant source 时，只在 query 明示状态演化、前后变化或时间
  序列时准入 successor；
- mixed-role packet 中已有 source 的相对顺序保持不变，新 source 按 episodic strength 稳定
  插入；
- 没有 eligible relation 时逐项返回原 activation，不增加 Reader/Judge 或生成式逻辑。

这是一条输入结构与 query 语义上的通用边界。运行时代码不知道数据集、operation、题号、
答案或 scorer 字段。所有冻结评测继续使用 Qwen3.6-27B Reader、MiniMax-M3 Judge、24K
Reader input 和原 repetition 顺序。

### STALE sealed：PASS，旧能力精确保留

最终工件与 0.10.0 冻结工件 SHA256 完全相同：
`20646f400b5b8a6088596a9558d4e225c8bcf356ae0c856266a0678cbf5191b1`。

| 指标 | Top-10 | Top-20 | Top-40 |
| --- | ---: | ---: | ---: |
| Latest Recall Δ | +4.17pp | +3.33pp | +1.67pp |
| Stale Exposure Δ | 0.00pp | 0.00pp | 0.00pp |

240 个 query 的逐行结果与原冻结版本完全一致，说明安全修订没有用下游非退换掉 Mneme5 的
正式 successor-recall 能力。

### MemOps Answer：PASS

840 题中 823 题 context 与 0.9.2 逐字节相同，17 题发生 source membership 变化，
order-only 变化为 0。三轮配对结果：

| repetition | Accuracy Δ | Token-F1 Δ | wins / losses / ties |
| --- | ---: | ---: | ---: |
| 0 | 0.000pp | +0.015pp | 0 / 0 / 840 |
| 1 | 0.000pp | -0.022pp | 1 / 1 / 838 |
| 2 | 0.000pp | +0.027pp | 1 / 1 / 838 |
| mean | **0.000pp** | **+0.007pp** | 0.67 / 0.67 / — |

Operation 均值为 Forget `+0.230pp`、Reflect `0.000pp`、Remember `0.000pp`、
TrajectoryOps `-0.190pp`、Update `0.000pp`，全部通过冻结非劣门。没有缺失答案、解析失败或
超 24K 输入。

### LongMemEval-S Answer：PASS

500 题中 425 题 context 与 0.9.2 逐字节相同，75 题变化；最大 Reader input 为 23,986
tokens。reader-free 24K Recall `+0.160pp`，complete recall `+0.213pp`。三轮 Answer：

| repetition | Accuracy Δ | Token-F1 Δ | wins / losses / ties |
| --- | ---: | ---: | ---: |
| 0 | +0.600pp | +0.807pp | 5 / 2 / 493 |
| 1 | +0.200pp | +0.500pp | 4 / 3 / 493 |
| 2 | 0.000pp | +0.188pp | 4 / 4 / 492 |
| mean | **+0.267pp** | **+0.498pp** | 4.33 / 3.00 / — |

### 构建、API 与冻结工件

- 最终核心 commit/tag：`9d8d170` / `v0.10.1`；API commit/tag：`6cd9420` / `v0.3.0`；
- 核心：`345 tests passed`，`git diff --check` PASS；
- wheel/sdist：`mnemekit-0.10.1` 构建并通过 `twine check`；
- API：精确固定 `mnemekit==0.10.1`，安装候选 wheel 后 `7 tests passed`；
- PyPI 0.10.1 已上传，公开 wheel/sdist digest 与本地冻结构建一致；全新 venv 只安装
  `mneme-api` wheel 后自动获得公开 `mnemekit==0.10.1`，Add/Search smoke 返回 2 items、
  latest-first；
- MemOps context/report SHA256：`5bd543c2...cbb739` / `fb07b830...4656`；
- LME context/report SHA256：`455ef126...f8337` / `e8a103be...6063f`；
- wheel/sdist SHA256：`b9bc82d4...99dd` / `56d387c5...f3bd`。

最终判定：**0.10.1 冻结回放 GO**。剩余步骤只包括提交发布、PyPI 回装、API wheel 构建、
远端官方 Smoke 和部署稳定性观察；不得再修改算法、阈值、prompt 或冻结数据协议。以下
2026-10-24 的 0.10.0 NO-GO 分析继续保留，作为本次修复的可追溯依据。

## 0. 比赛负责人验收进度（2026-10-24）

核心方的交付边界已结束于正式 package 发布；以下均由比赛 API 方独立验收。

### 0.1 API 接入：PASS

- `mneme-api` 候选版本更新为 `0.3.0`，精确固定 `mnemekit==0.10.0`；
- Search 仍调用既有 `search_composed_evidence()`，无第二套 Mneme5 逻辑；
- metrics 新增 `evolution_route` 与 `evolution_source_count`，不记录 query 或原文；
- Add 批次形成 evolution episode，API 行为测试中 successor route 成功触发；
- Health、Add、Search、鉴权、幂等、user 隔离、恢复和 100K token 边界共 `7 passed`；
- 首次隔离 wheel smoke 发现 API metadata 未声明英文必需的 `en_core_web_sm`，导致只安装
  wheel 时英文 Add/Search 返回空结果；API 已补入与 lock 文件相同的 3.8.0 精确依赖，
  successor 测试也加强为必须返回两条原始证据且新值排在前面；
- 修复后 API 0.3 wheel/sdist 构建成功；全新 venv 只安装 wheel 即自动获得
  `mnemekit==0.10.0` 与 `en-core-web-sm==3.8.0`，Add/Search smoke 返回 2 items、最新值第一、
  `evolution_route=true`；
- 当前改动保留在本地候选工作树，尚未部署或推送，不影响正在使用的 0.9.2 服务。

### 0.2 真实 1.57 GiB Store 配对：首轮 PASS

使用保留的 1,112-history 原始 Store、0.10.0 迁移副本和 6 条固定私有 query，同机串行比较
PyPI 0.10.0 与保留的 0.9.2 wheel。两边均使用 API 的 `o200k_base`、Top-100、100K
atomic-source budget 与相同 response formatter。

| 指标 | 0.9.2 | 0.10.0 | 倍率/结果 |
| --- | ---: | ---: | ---: |
| 首条冷读 Search | 119.048s | 120.529s | 1.012x |
| 6 条 Search 中位 | 9.457s | 9.811s | 1.037x |
| 后四条热段范围 | 7.612–9.656s | 7.805–10.264s | 同量级 |
| 峰值 RSS | 791,708 KiB | 795,612 KiB | 1.005x |
| swap | 0 | 0 | PASS |
| response parity | — | 6/6 SHA256 相同 | PASS |

6/6 query 的 item 数、span 数、Evidence token 数和完整 API response digest 全部一致。
该旧 Store 只有一个迁移后的 legacy episode，因此 `evolution_source_count=0`；它验证的是
兼容路径和资源非退化。新 Store 的 successor 触发由独立 API 行为测试覆盖。

### 0.3 大规模门审计

Memora validation 的实际输入审计为 2 personas × 3 periods、42,104 sources、120
questions，六个目录合计约 23.6 MiB。完整 Reader/Judge 还涉及
MemOps 840、LoCoMo 1,986、LongMemEval-S 500 题及三次 repetition，会产生外部模型调用和
新的结果缓存。用户已在审计规模后明确授权启动。

### 0.4 Memora validation：PASS

获得用户明确授权后，一次性打开冻结的 2 personas × 3 periods validation，使用发布版
production route、`activation=0.25`、`seed_events=10`，共 42,104 sources、120 questions。

| 指标 | Top-10 | Top-20 | Top-40 |
| --- | ---: | ---: | ---: |
| Current Recall Δ | −0.285pp | −0.221pp | −0.041pp |
| Stale Exposure Δ | −0.278pp | −0.278pp | 0.000pp |
| Stale Any Δ | −0.833pp | 0.000pp | 0.000pp |

三档 current recall 均在冻结的 `−1pp` 门内；stale exposure 和 stale-any 均未增加。
validation 判定 PASS。结果只用于比赛放行，不反向调整 relation threshold、margin、strength
或 seed 数。

### 0.5 LongMemEval-S Reader/Judge：PASS，带局部风险

使用冻结的 0.9.2 context、Qwen3.6-27B Reader、MiniMax-M3 Judge、24K Reader input、
Top-40 source admission，比较 0.9.2 与 0.10.0。500 题中 382 题 context 改变，118 题
逐字节不变；逐字节不变题直接复用冻结答案，变化题独立运行三次。所有输入均不超过 24K。

| 指标 | 0.9.2 三轮均值 | 0.10.0 三轮均值 | Delta |
| --- | ---: | ---: | ---: |
| Accuracy | 49.267% | 49.400% | +0.133pp |
| Token-F1 | 42.940% | 43.147% | +0.207pp |

三轮 Accuracy delta 为 `+0.20/+0.40/-0.20pp`，整体 PASS。分组均值中
temporal-reasoning `+0.525pp`、single-session-assistant `+1.190pp`，但
knowledge-update 为 `-2.315pp`。这不是整体阻塞项，但必须与 MemOps Update/TrajectoryOps
回归一起处理，不能宣称更新类能力全面提高。

### 0.6 MemOps Reader/Judge：NO-GO

使用相同 Reader/Judge、24K input、Top-100 和三次 repetition。840 题中 482 题 context
改变，358 题逐字节不变；相同 context 直接复用对应 repetition 的冻结答案。结果如下：

| 指标 | 0.9.2 三轮均值 | 0.10.0 三轮均值 | Delta |
| --- | ---: | ---: | ---: |
| Accuracy | 41.230% | 40.079% | **-1.151pp** |
| Token-F1 | 26.121% | 26.328% | +0.207pp |

三轮 Accuracy delta 为 `-2.262/0.000/-1.190pp`；第一轮 sign-test `p=0.0145`。
分组平均变化：

| Operation | Accuracy Delta |
| --- | ---: |
| Forget | 0.000pp |
| Reflect | -0.159pp |
| Remember | 0.000pp |
| TrajectoryOps | **-4.381pp** |
| Update | **-1.344pp** |

TrajectoryOps 在三轮中分别下降 `-6.286/-3.429/-3.429pp`，属于稳定结构性回归。按题型
聚合，trajectory_reasoning `-3.810pp`、target_binding `-2.778pp`、
downstream_application `-2.183pp`、operation_trace `-1.984pp`，只有
state_reasoning `+1.786pp` 和 distractor_control `+0.251pp` 为正。

回归也不能归因于单纯扩大 context：330 道变化题改变了 source membership，三轮变化样本
平均 `-1.919pp`；152 道题 source 集合完全相同、只有顺序变化，仍平均 `-2.193pp`。
11 道题三轮持续 loss，其中 5 道属于 TrajectoryOps。说明 forward successor activation
提高最新状态可见性时，会把局部 successor 提前到完整轨迹、身份绑定或下游计算所需证据
之前；即使 Top-100 内 source 集合不变，Reader 对顺序也足够敏感。

最终判定：**0.10.0 不进入第二次 Full**。下一候选必须保持 0.10.0 的新状态召回，同时对
trajectory/identity/compositional query 增加通用的 evidence-order preservation 或
composition-aware admission，并使用完全相同的冻结 context、三轮 Reader/Judge 重新过门。
不能针对 MemOps、operation label、question ID 或上述 11 道题写特判。

### 0.7 冻结产物与完整性

所有产物仅保存在本地 ignored `.runtime/`，报告目录也由 `.git/info/exclude` 排除，禁止推送。

| 产物 | 行数 | SHA256 |
| --- | ---: | --- |
| `gate-b-lme-0.10.0.jsonl` | 500 | `06ce83c9...6551b5eb7` |
| `mneme5-lme-answer-gate.json` | — | `9a1634da...db30cec` |
| `memops-package-heldout-memory-0.10.0.jsonl` | 840 | `616e6825...655bb2b` |
| `mneme5-memops-answer-gate.json` | — | `ee5fa784...47b2527d` |

三轮 LME cache 各 1,000 行，三轮 MemOps cache 各 1,680 行；每轮均包含完整 baseline 与
candidate population。API 最终回归为 `7 passed`，API 与核心评测改动均通过
`git diff --check`，三个本地评测脚本均通过 Python 编译检查。

## 1. 目标

本文回答两个不同问题：

1. 哪一部分 Mneme5 研究结果可以尽快成为比赛升级版；
2. 完整的 dependency-directed persistent revision 还需要哪些证据。

比赛升级的最低目标不是证明 Mneme5 论文全部成立，而是在保持 Mneme 0.9.2 已通过的
Answer 质量、API 契约、性能和安全边界的同时，提高当前状态、时间演化和更新类问题的
证据可用性。

第二次 Full 只能使用冻结的单一版本。从 Add 开始到评测结束，不得在任务中途升级核心、
迁移 schema、改变阈值或切换 Search 语义。

## 2. 当前证据与缺口

### 2.1 已有正向证据

forward successor activation 在真实
`AtomicIndex -> ActivationField -> EvidenceComposer` 全链路上的 Latest Recall 结果：

| Split | Top-10 | Top-20 | Top-40 | Stale exposure |
| --- | ---: | ---: | ---: | ---: |
| STALE development | +7.92pp | +6.94pp | +6.81pp | -0.14/-0.14/0.00pp |
| STALE opened validation | +7.92pp | +6.67pp | +6.25pp | 0.00/0.00/0.00pp |

六个 scenario-paired 95% interval 均高于零。Type I 直接更新和 Type II 依赖失效在三个
预算上都提高。forward 方向也比 bidirectional activation 更安全，因为它没有增加平均
stale exposure。

冻结后的 STALE sealed held-out 也已通过：Latest Recall@10/20/40 分别提高
`+4.17/+3.33/+1.67pp`，Top-20 的 scenario-paired 95% interval 为
`[+0.42,+6.67]pp`，三档 stale exposure 均不增加。五个 Mneme1--4 legacy population
以及 8K/24K/100K token-budget 回归均通过预设的 `-1pp` 非退化门。

同时必须保留一个比赛边界：STALE sealed 在 8K/24K/100K token admission 下 Latest Recall
均与 baseline 持平。AML Search 实际使用 Top-100 与约 100K Evidence token，因此论文中的
紧 Top-K 增益不自动等于 AML Answer 增益。LongMemEval-S 的三档 token Recall 约提高
`+0.93pp`，说明并非所有实际预算都 no-op，但是否值得消耗唯一剩余 Full 必须由 AML 风格
回放和 Reader/Judge 决定。

### 2.2 当前阻塞项

当前结果不能直接用于比赛，决定性原因及后续工程项如下：

- 最终候选相对 0.9.2 的 Qwen Reader / MiniMax Judge 已完成；MemOps Accuracy 三轮平均
  `-1.151pp`，未通过冻结的 `-1.00pp` 非退化门；
- 真实 1.57 GiB AML Store 的 6-query 配对已通过，但尚未完成长时间 RSS、批量 Add P95
  和中断迁移恢复；
- `mnemekit==0.10.0` 已正式发布，但 `mneme-api` 的 0.10.0 接入仍只在本地候选工作树，
  尚未形成最终 API commit 或远端部署；
- 尚未完成远端迁移、长历史定向 Search、稳定性观察和官方 Smoke；
- Memora tuning 与一次性 validation 均通过；held-out 未打开，因为 Answer 门已先行失败，
  没有继续消耗 sealed 资产的必要。

完整 persistent revision 仍不是本次比赛候选：active-head suppression、terminal
freshness、unaffected preservation 与 rollback 没有完成。Route A 明确保留全部旧证据，
因此这些 Route B 缺口不阻塞 Route A，但也不能随发布顺带进入。

核心发布账本已经把 0.10.0 登记为 `ALG-DDR-1 / Mneme5 directional successor recall`，
并明确把 AML/Reader/Judge 保留为独立比赛门。五个未跟踪评测文件未进入 wheel/sdist，
不再阻塞核心 package；它们继续按研究资产边界留在本地。

### 2.3 2026-10-24 比赛实现进展

路线 A 已完成公共核心实现，方法 commit、候选版本和 sealed protocol 均已冻结：

- relation 改为无需全历史 IDF 的 4-character `char_wb` sublinear-TF；
- relation 单位是 Add 批次 episode，不改原始 session event；这避免真实 Store 的单个
  2,500-source event 被每次 Add 整体重算；
- relation threshold、margin、activation 保持 `0.20 / 0.05 / 0.25`；
- 只有 query 排名前 10 个 event 可以向 successor 传播；
- relation、fingerprint、倒排 posting 与 successor 均可事务化持久；
- Search 冷开读取现有 namespace，不为 query 重新 fit；
- 没有 relation 或 route 未触发时返回原始 activation，不做 suppression；
- schema 仍为 3；旧 Store 只读打开不会隐式创建 evolution namespace，显式
  `migrate_store()` 才 backfill。

production-mode development 结果为 Latest Recall@10/20/40
`+4.17/+3.75/+1.67pp`，stale exposure `-0.14/0.00/0.00pp`；Top-20 paired
95% interval 为 `[+2.36,+5.28]pp`。relation precision 为 `73/75=97.33%`。
Memora tuning 的 current recall 为 `-0.28/-0.13/-0.07pp`，stale exposure 为
`0.00/-0.08/-0.01pp`，已消除原 Top-10 `-8.23pp` 风险。

当前 Gate 状态：Gate 0 核心 commit、版本与 tokenizer hash 已冻结；Gate 1 核心实现与
API 本地接入 PASS；Gate 2 STALE sealed PASS；Gate 3 Memora validation PASS；Gate 4
legacy reader-free PASS；Gate 5 LongMemEval-S PASS、MemOps FAIL；Gate 6 真实 Store 6-query
性能配对 PASS；Gate 7 因 Gate 5 失败而不启动。因此研究状态为 PASS，比赛状态为确定的
NO-GO。详见 `mnemekit-0.10.0-mneme5-gate-0-1-20261024.md`。

### 2.4 Gate 2 一次性结果

STALE sealed held-out 的主统计门通过：Latest Recall@10/20/40 为
`+4.17/+3.33/+1.67pp`，Top-20 paired 95% interval 下界为 `+0.42pp`，三档 stale
exposure 均不增加，relation precision 为 `96.77%`。但 source-count parity 仅为
Top-10 `240/240`、Top-20 `238/240`、Top-40 `224/240`。所有 mismatch cell 的 recall
delta 都是 0。

早期门禁把“相同 Top-K 上限”误写成“实际返回数量必须完全相同”，从而曾将本项判为
NO-GO。该口径现已纠正：排行榜协议约束的是相同的 Top-K/token 上限，不要求不同检索器在
baseline underfill 时返回相同数量；而且 18 个 count-mismatch cell 的 headline recall
均为 tie，收益不是靠额外 source 数制造。因此 Gate 2 最终判定 **PASS**，数量差异作为
Analysis 透明保留。

## 3. 两条发布路线

### 3.1 路线 A：比赛优先的安全升级

只发布 query-time forward successor activation：

- 建立同 owner、跨 event、严格按时间从旧到新的 `related_event` 候选；
- 查询激活旧 event 时，只给 later event 增加 episodic activation；
- 原始 source 永久保留；
- 不删除旧 source；
- 不切换 persistent active head；
- 不执行 stale suppression；
- 不把 `related_event` 宣称为 `supersedes`；
- 固定 Top-K 与 token budget，不额外扩大 Reader 输入。

这是当前最有机会在 10 月 30 日前完成的比赛升级。它应以新的算法版本发布，而不是
0.9.2 patch，因为它会改变 Evidence 排序。

### 3.2 路线 B：完整 Mneme5 persistent revision

在路线 A 之外增加：

- exact `StateKey`；
- typed value 与 validity；
- `same_slot`、`supersedes` 和 active head；
- reverse dependency closure；
- unaffected-use preservation；
- rollback 与 deterministic replay；
- transactionally persisted revision metadata。

路线 B 在 terminal freshness、unaffected preservation 和 rollback 全部通过前不得进入比赛。
如果时间不足，应发布路线 A，不能把未完成的 suppression 混入。

## 4. Gate 0：方法与版本冻结

运行任何 sealed 结果前，必须冻结：

1. 核心 commit、API commit、package version 和 schema version；
2. relation threshold `0.20`、margin `0.05`、activation `0.25`；
3. forward-only 方向；
4. relation 的 owner、event 和 chronology 约束；
5. query route 与不触发 route 的条件；
6. Top-10/20/40、8K/24K/100K 的计量方法；
7. tokenizer identity 与 hash；
8. 所有 dataset split、指标、denominator、bootstrap seed 与通过阈值；
9. legacy non-regression 与 Answer gate；
10. 真实 Store 性能门禁。

方法不得读取 answer、gold evidence、benchmark 名称、question ID、Type I/II 标签、
operation label 或 scorer-only 字段。代码不得包含 STALE、Memora 或 AML case 规则。

## 5. Gate 1：核心实现与 API 接入

### 5.1 核心实现

比赛候选必须进入 `mneme/` 公共核心，不能由 API 复制 `eval/` 代码。最低要求：

- relation metadata 有明确的数据结构和确定性顺序；
- Add 时增量更新或迁移时一次性构建 relation index；
- Search 不得为每个 query 对完整历史重新 fit TF-IDF；
- Store 冷开直接读取已持久化索引；
- 重复 Add 按 request ID 幂等后 relation 也保持幂等；
- 相同 Store、query 和版本的 Evidence digest 可重复；
- 原始 source、role、timestamp、event、exchange 和 source ID 不改变；
- 未触发 successor route 的 query 与 0.9.2 Evidence 逐字段一致；
- migration 前后 Evidence 和 relation digest 一致；
- migration 失败可 rollback，不留下半迁移 schema。

如果实现需要 schema bump，必须提供从 schema 3 的显式迁移。只读打开不得偷偷修改 Store。

### 5.2 API 契约

`mneme-api` 继续满足：

- `/health`、`/add`、`/search` 协议不变；
- Search 返回完整原始 turn，不返回摘要或生成文本；
- `top_k=100` 仍是最多 100 个 source item；
- API 按最终渲染格式使用 `o200k_base` 严格限制 100,000 Evidence tokens；
- 超大 source 整项跳过，后续较短 source 仍可接纳；
- `user_id` 隔离、request ID 幂等和同步 Add 可见性不变；
- API 固定精确 package version，不使用浮动依赖；
- metrics 记录版本、route、item/span/token 数、耗时和 Evidence digest，不记录完整 query。

## 6. Gate 2：STALE sealed held-out

方法、阈值和实现冻结后，一次性打开预留的 80 个 STALE held-out scenarios、240 个 query。

路线 A 必须同时满足：

1. 主预算 Top-20 Latest Recall 相对 0.9.2 提高至少 `+2.00pp`；
2. Top-20 scenario-paired 95% interval 下界大于 `0`；
3. Top-10 与 Top-40 Latest Recall 均不得下降超过 `1.00pp`；
4. Top-10/20/40 mean stale exposure 均不得增加；
5. Type I 和 Type II 在三个预算中都不得出现超过 `1.00pp` 的明显退化；
6. accepted relation precision 至少 `95%`；
7. wrong-owner 和 cross-identity relation 为 `0`；
8. 使用相同 Top-K 上限；若一方因候选不足而 underfill，必须报告实际数量差异，并证明
   headline 收益不是由放宽上限或额外 Reader token 制造；
9. 所有 scorer-only 字段只能在 retrieval 冻结后使用；
10. 完整 population、wins/losses/ties 和 paired interval 全部报告。

任何一项失败都不能用 development/opened-validation 的大幅收益补偿。

## 7. Gate 3：Memora 安全迁移

早期全历史 TF-IDF event propagation 曾在 Memora tuning 出现 Top-10 `-8.23pp`，因此这是
比赛升级的关键安全门。当前冻结的增量 4-gram Route A 已把 tuning 变化收敛到
`-0.28/-0.13/-0.07pp`，且 stale exposure 不增，但仍需预留 split 作外部确认。不能按
数据集名称关闭功能；必须由通用 owner/event/chronology 或 route 条件决定是否 abstain。

先在尚未打开的两个 Memora validation personas 一次性验证。通过后才允许打开三个
held-out personas。每个阶段均要求：

1. current-source Recall@10/20/40 均不得下降超过 `1.00pp`；
2. forgotten/stale-source exposure 不得增加；
3. unaffected obligation source ranking 必须 `100%` 保持；
4. wrong-owner relation 为 `0`；
5. 没有满足通用安全条件时必须回退为 0.9.2 排序；
6. 不允许针对 persona、weekly/monthly/quarterly 或 operation 类型分支；
7. validation 失败即 NO-GO，不继续打开 held-out 调参。

路线 A 不要求提高 Memora，但必须证明不会重复 tuning 上的明显退化。

## 8. Gate 4：Mneme1–4 legacy non-regression

使用冻结的 LoCoMo、LongMemEval-S、BEAM-100K、MemOps 与 SocialMemBench 评测资产，比较
0.9.2 与候选版本。不同数据集不得合并成一个总均值。

### 8.1 Reader-free

- 所有不触发 successor route 的 query，source sequence 和 Evidence digest 必须完全一致；
- 每个数据集 Recall/Any/Complete@10/20/40 的下降不得超过 `1.00pp`；
- 每个数据集 8K/24K/100K Recall/Any/Complete 的下降不得超过 `1.00pp`；
- 0.9.2 已饱和的 100K cell 不得出现实质退化；
- A/G/H 对应的直接事实、执行和安全代理切片不得出现超过 `2.00pp` 的稳定下降；
- 报告 route 覆盖率，避免“平均不退化”由大量 no-op query 掩盖 route 内损失。

### 8.2 定向能力

至少单列：

- MemOps Update、Forget、TrajectoryOps；
- LongMemEval temporal reasoning、knowledge update、preference；
- SocialMemBench state/evolution；
- 单 source 与 multi-source；
- current/latest query 与 history/change query。

定向切片用于发现风险，不能替代全量 non-regression。

## 9. Gate 5：Qwen Reader / MiniMax Judge Answer 非劣

只有 Gate 2–4 reader-free 全部通过后才运行 Answer gate。比较对象是冻结的 0.9.2 与最终
候选，不是开发过程中的中间版本。

使用现有相同配置：

- Reader：`Qwen/Qwen3.6-27B`；
- Judge：`MiniMax-M3`；
- 完整 prompt cap：24,000 tokens；
- 三次独立 repetition；
- 相同 reader/judge prompt、question order distribution、rubric 和 complete-source admission；
- 按题配对报告 accuracy、token F1、wins/losses/ties 和 sign test。

至少运行：

1. MemOps 840 题 package gate；
2. LoCoMo 1,986 题，headline 使用 category 1–4 的 1,540 题；
3. LongMemEval-S 500 题；
4. STALE held-out 的 answer-level transfer，若数据提供可冻结 reference/rubric；
5. update/temporal/preference 定向切片。

非劣规则沿用 0.9.2 release gate：

- 每个数据集 mean accuracy 和 headline token F1 相对 0.9.2最多下降 `1.00pp`；
- 任一数据集不得在三次中有两次下降超过 `2.00pp`；
- 样本数至少 100 的主要切片 mean accuracy 最多下降 `3.00pp`；
- timeout、空答案、Reader parse failure 与 Judge verdict failure 不得增加；
- MemOps、LoCoMo、LongMemEval 与 STALE 分别判定，不得 pooling；
- target update/temporal slice 若稳定退化，即使总体通过也不得作为 Mneme5 升级发布。

不要求新候选显著超过 0.9.2；比赛放行的底线是没有明显 Answer 质量下降。

实际执行结果：LongMemEval-S 整体 PASS；MemOps 因三轮平均 Accuracy `-1.151pp` FAIL，且
TrajectoryOps 三轮稳定下降。LoCoMo headline 的冻结 retrieval/source context 与 0.9.2
逐题完全相同，因此不重新调用随机 Reader/Judge；相同 prompt 的预期配对 delta 严格记为
零。Gate 已被 MemOps 明确否决后，不再消耗 STALE answer-level 或 Memora held-out 等 sealed
资产。完整数值和归因见 0.5–0.6。

### 9.1 唯一剩余 Full 的额外价值门

上述非劣标准足以判断 package 安全，却不足以决定是否消耗唯一剩余 Full。正式替换 0.9.2
还必须满足以下价值证据：

1. 使用首轮 Full 已保存的脱敏 Add/Search 请求，分别从空 Store 构建 0.9.2 与最终候选；
2. 报告 successor route 覆盖率、返回 JSON 变化率、Reader 可见前 100K token 变化率，以及
   successor source 实际进入或前移到可见前缀的 query 数；
3. 对发生可见变化的 query 分开报告 item/span/token、延迟、Evidence digest 与 source
   顺序，不能仅用全量大量 no-op query 的平均数掩盖；
4. 至少一个与 AML 弱项对应的冻结 Answer 切片（优先 LongMemEval 时间/更新或 MemOps
   Update）mean accuracy 或 token F1 相对 0.9.2 为正；
5. 三个完整 Answer population 仍满足本节非劣门，且不能以某个小切片提升补偿总体退化；
6. 若真实 AML 回放的 Reader 可见前缀几乎不变，或 Answer 只有噪声级波动，则第二次 Full
   继续使用 0.9.2，不因论文 novelty 单独升级。

首轮请求仅用于部署连续性与可见性回放，不得读取官方答案、评分标签或用其调 relation
阈值；最终方法继续固定为 `76715e6`。

## 10. Gate 6：真实 Store 性能与资源

使用保留的 1.57 GiB、1,112-history AML Store 和固定私有 query 做同机配对。不得发布
query、source ID 或原文。

### 10.1 Search

- 冷读 Search 不超过 0.9.2 的 `1.25x`；
- 热页 P50/P95 不超过 0.9.2 的 `1.25x`；
- 单次 Search 峰值 RSS 不超过 `1.35 GiB`；
- 连续 100 次 Search 后 RSS 不得持续单调增长；
- 2 GiB 服务器、业务并发 1 下不得出现 OOM、swap thrash 或 30 分钟平台超时；
- relation 构造、relation 读取、activation、composition、budget 与 formatting 分阶段计时；
- route 未触发时不应为 relation expansion 支付完整历史扫描成本。

### 10.2 Add 与存储

- 1K/10K Add P95 相对 0.9.2 不超过 `2x`；
- 10K 冷启动目标小于 `1s`；
- schema 3 迁移峰值内存必须适合 2 GiB 服务器；
- 迁移前后原始 Evidence 完全一致；
- relation index 必须增量落盘，不能每次 Search 重建；
- 数据库增长量、迁移时间和追加写放大必须报告；
- 中断迁移后的恢复或显式 rollback 必须验证。

性能测试至少运行三次，区分首遍与热页，不用不同 page-cache 状态的单次数字作结论。

## 11. Gate 7：API、部署与 Smoke

发布前必须完成：

1. 核心完整测试；
2. wheel/sdist、Twine、PyPI 独立安装 smoke；
3. `mneme-api` 测试；
4. 空 Store、旧 schema 3 Store 和迁移后 Store 的 Health/Add/Search；
5. Add 后立即 Search 可见；
6. 重复 request ID 不产生重复 source/relation；
7. user 隔离；
8. 服务重启后 Evidence digest 一致；
9. 100K token 边界与超大 source 跳过；
10. 真实长历史定向 Search；
11. 远端 24 小时稳定运行，无 RSS 漂移、5xx 或 timeout；
12. 官方 Smoke 通过。

官方 Smoke 每小时只有一次机会，必须在本地和远端定向检查通过后再发起。

## 12. 完整 Mneme5 的附加硬门

如果比赛版本包含 persistent active head 或 stale suppression，除 Gate 0–7 外必须全部满足：

1. terminal source freshness `100%`；
2. terminal typed value correctness `100%`；
3. accepted `same_slot` precision至少 `95%`；
4. wrong identity / wrong target persistent revision 为 `0`；
5. tentative、plan、conditional 和 unresolved time 不得切 active head；
6. unaffected source ranking byte-identical，覆盖率 `100%`；
7. rollback 恢复旧 head、dependency output 和 digest，正确率 `100%`；
8. deterministic replay 与增量执行结果完全一致；
9. source immutability `100%`；
10. alternate support 存在时不得错误失效 dependent result；
11. transaction 失败不得留下部分 head 或 dependency closure；
12. STALE 与 Memora sealed held-out 均通过 persistent revision 主指标。

当前 terminal chain 结果未通过，因此在新的完整证据出来前，比赛版本禁止包含 suppression。

## 13. Go / No-Go 决策表

| 项目 | 当前状态 | 路线 A 要求 | 路线 B 要求 |
| --- | --- | --- | --- |
| Development Latest Recall | PASS | 保持 | 保持 |
| Opened validation | 正向但已暴露 | 仅作诊断 | 仅作诊断 |
| STALE sealed held-out | **PASS** | 已满足 | 必须 PASS |
| Memora safety | tuning 与 validation **PASS**；held-out 未打开 | 已满足 validation 门 | current/stale 明显改善 |
| 核心公共实现 | **PASS**，core `76715e6` | 已满足 | 必须完成 |
| Store/schema/migration | 首轮 PASS，完整工程门未完成 | 必须完成 | 必须完成 |
| Legacy retrieval | **PASS**，五数据集及三档 token budget | 已满足 | 必须非劣 |
| Answer gate | LME PASS；MemOps **FAIL (-1.151pp)** | 未满足 | 必须非劣 |
| 真实 AML Store 性能 | 6-query 配对 PASS；长期稳定性未完成 | 必须 PASS | 必须 PASS |
| Terminal freshness | FAIL | 不启用 suppression，可不阻塞 | 必须 100% |
| Unaffected preservation | 未完成 | route 外必须一致 | 必须 100% |
| Rollback | 未完成 | 不改 active head，可不阻塞 | 必须 100% |
| PyPI/API release | 核心 PyPI PASS；API 本地候选 PASS、未部署 | 必须完成 | 必须完成 |

### 当前决定

- 路线 A：**研究晋级 PASS、比赛 NO-GO**。Gate 2–4 已通过，但 Gate 5 的 MemOps Answer
  非退化门失败；0.10.0 不替换 0.9.2 参赛。
- 路线 B：当前明确 NO-GO；terminal freshness、preservation 和 rollback 通过前不得参赛。
- 第二次 Full 当前继续使用已通过首轮官方评测的 0.9.2；只有新的 successor 排序候选在
  同一冻结协议下修复 MemOps 后，才重新考虑升级。

## 14. Full 提交策略

1. 先在本地冻结最终候选和全部报告；
2. 部署到独立数据目录，不复用首轮完成任务的运行状态；
3. 完成远端 Health/Add/Search、长历史验证和 24 小时稳定性观察；
4. 官方 Smoke 通过后保持部署不变；
5. 10 月 30 日开放后，从 Add 开始提交第二次 Full；
6. Full 期间不升级、不改阈值、不迁移、不清空 Store；
7. 保留 API commit、package tag、配置 hash、镜像或环境锁文件和 Search metrics；
8. 如果出现失败，只修复不改变 Evidence 的运维问题并从原 checkpoint 续跑；算法变化留给新的合法 Full 机会。

同一个 AML Key 已完成第一次 Full，按现有规则只剩一次第二次 Full。若希望对新版运行更多
正式 Full，应先向主办方确认是否存在新的合规系统/Key 配额；不能把额外账号默认视为可用
评测额度。

## 15. 比赛 API 方的剩余交付清单

核心 package 已完成交付。比赛侧按以下顺序验收和部署路线 A：

1. ~~把 forward successor activation 从 `eval/` 提升为核心、持久、增量实现；~~ 已完成。
2. ~~冻结 commit、schema、阈值、route 和 sealed protocol；~~ 已完成。
3. ~~跑 STALE held-out；~~ 已通过。
4. ~~跑 legacy reader-free non-regression；~~ 已通过。
5. 一次性跑 Memora validation，确认不重复早期 Top-10 退化；held-out 可作为最终外部确认，
   但不得在 validation 结果之后改方法再使用同一 held-out 宣称 untouched。
6. 跑 0.9.2 对照的三套 Answer gate；STALE answer transfer 若具备可靠 reference/rubric 再加。
7. 真实 AML Store 6-query 冷/热配对已通过；继续补连续 Search RSS、批量 Add 与迁移恢复门。
8. ~~发布 PyPI 0.10.0；~~ 已完成。固定最终 API commit，并部署经过测试的 API 0.3 接入。
9. 在全新/旧 schema 3/迁移后 Store 上完成远端稳定性与官方 Smoke。
10. 全部门禁通过后才替换 0.9.2；任何失败都保留 0.9.2 作为第二次 Full fallback。

完整 Mneme5 的 active-head、suppression 和 dependency closure 继续独立开发，不阻塞安全的
query-time successor 候选，也不允许搭便车进入比赛版本。
