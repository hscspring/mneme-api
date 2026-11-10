# Mneme 0.9.x Source-Atomic Budget 路径性能优化需求

日期：2026-10-14\
优先级：下一次 AML Full 前的性能门禁\
目标版本：基于 `mnemekit 0.9.1` 的后续兼容版本\
性质：等价性能优化，不改变 Mneme4 算法与 Evidence 语义

## 1. 结论

Mneme4 的 `search_composed_evidence()` 已满足比赛需要的 source-atomic 输出和严格
100K token 预算，但真实长历史 Store 暴露了新的重复 tokenization：预算达到上限后，
`SourceEvidenceProjector` 仍需检查后续候选；每检查一个候选，当前实现都会重新测量
已经接纳的完整 Evidence 集合。

在保留的 AML 真实极端 Store 上，单条 Search 共调用预算测量 2,500 次，累计重复访问
131,010 个 Evidence item，其中 token 计量本身耗时 54.692 秒。0.9.1 总 Search 耗时
165.992 秒，而 0.8.3 兼容路径为 118.793 秒。

需求是在完全保持 0.9.1 返回结果的前提下，让 source-atomic 路径对每个候选的文本最多
tokenize 一次，避免反复 tokenize 已接纳前缀。

## 2. 复现对象

### 2.1 版本

- `mnemekit 0.8.3`：旧比赛路径的兼容基线。
- `mnemekit 0.9.0`：首次发布 Mneme4 source-atomic composition。
- `mnemekit 0.9.1`：当前最新版，Git tag `v0.9.1`，commit `90b5207`。
- `mneme-api`：commit `642d4b2`，调用 `search_composed_evidence()` 并传入
  `scope_owner="user"`。
- Tokenizer：`o200k_base`。
- Evidence budget：按 API 最终渲染格式计量，limit 为 100,000 tokens。
- `topn`：100。

### 2.2 私有复现数据

复现使用本地忽略目录中的 AML 私有快照：

```text
/mnt/sv0/sean/research/Mneme/.runtime/full-store-1112-20261010/
```

Store 特征：

- 数据库约 1.57 GiB；
- 1,112 个 history requests；
- schema 3；
- 查询来自原 Full 的已保存极端 Search；
- 私有 query、原文和 source ID 不进入本文档，也不得提交到仓库。

## 3. 配对结果

同一 Store、同一 query、同一机器的结果如下：

| 路径 | Search 耗时 | Items | Spans | Evidence tokens |
| --- | ---: | ---: | ---: | ---: |
| 0.8.3-compatible `search_evidence()` | 118.793 s | 1 | 51 | 101,236 |
| 0.9.0 `search_composed_evidence()` | 159.646 s | 52 | 52 | 99,962 |
| 0.9.1 `search_composed_evidence()` | 160.661 s | 52 | 52 | 99,962 |
| 0.9.1，带预算计量 profile | 165.992 s | 52 | 52 | 99,962 |

0.9.1 输出满足预期：

- 一项对应一个完整原始 source；
- 严格不超过 100K；
- 与 0.9.0 的 source digest 完全一致；
- 与旧路径的前 10 个 source 完全一致；
- 旧路径 51 个 source 中保留 50 个，并额外接纳 2 个 source；
- 0.9.1 复现 source digest 为
  `137e621b1cbde0961feac2c7d06658bc9caae98770dd1c07ff321df345e8a1d2`。

因此当前问题是性能问题，不是检索正确性问题。

## 4. 根因

当前 `SourceEvidenceProjector` 的核心行为等价于：

```python
for source_id in composition.source_ids:
    item = project(source_id)
    if budget.reached([*evidence, item]):
        continue
    evidence.append(item)
```

这个 `continue` 语义是必要的：某个较长 source 放不下时，后面更短的 source 仍有机会
被接纳。因此不能在第一次超预算时直接停止。

问题在于 `EvidenceBudget.measure()` 接收整个累计 tuple。API 当前的 measure 会遍历 tuple
中的每一个 item，并重新对渲染后的 content 执行 `o200k_base` tokenization。预算接近满载
后，每个未接纳候选都会触发“约 52 个已接纳 item + 当前候选”的完整重复计量。

真实 profile：

| 指标 | 结果 |
| --- | ---: |
| Composition 候选数 | 2,500 |
| Budget measure 调用数 | 2,500 |
| 最大单次测量 item 数 | 53 |
| 累计 item visits | 131,010 |
| Budget measure 总耗时 | 54.692 s |
| Search 总耗时 | 165.992 s |

预算计量约占整条 Search 的 32.9%。

## 5. 必须保持的语义

优化不得改变以下行为：

1. `CompositionResult.source_ids` 的顺序和内容不变。
2. 每个返回项仍只包含一个完整原始 source。
3. `source_id`、role、timestamp、event、exchange、access path、strength 和 channels 不变。
4. 第一批已接纳 Evidence 与 0.9.1 完全一致。
5. 单个 source 超预算时整项跳过，不允许截断 source 文本。
6. 跳过超预算 source 后仍继续检查后续 source。
7. 返回 item 数不超过 `topn`。
8. 最终 API 渲染后的 Evidence tokens 严格不超过调用方预算。
9. 没有 budget 时的结果不变。
10. 现有 `search_evidence()` 与其他 projection 行为不变。

这不是调整 protected prefix、重排策略、participant scope 或 cascade 的机会。任何 Evidence
变化都应作为独立算法候选评估，不能合入本性能修复。

## 6. 建议的实现边界

核心接口目前允许任意 tuple-level `measure`，不能默认所有计量函数都满足 item token 数可加。
建议保留现有通用路径，并为可加预算增加显式能力，例如：

- 给 `EvidenceBudget` 增加可选的单 item measure；或
- 增加明确标记为 additive 的 budget 实现；或
- 提供等价的增量 admission 接口，由调用方返回单 item 成本。

在 additive 路径中：

1. 每个 projected item 的成本只计算一次；
2. 保存 running total；
3. 用 `running_total + item_cost <= limit` 决定 admission；
4. 超预算时不增加 running total，并继续后续候选；
5. 非 additive 的旧调用方继续使用兼容 fallback。

API 的当前计量是各 Evidence item 渲染文本 token 数之和，天然满足可加条件。缓存必须是
单次 Search 生命周期内的请求级缓存，避免跨请求长期保留 Evidence 文本或造成新的内存增长。

如果核心暂时不扩展接口，API 侧也可以用请求级 item-token 缓存作为过渡方案；正式方案仍
建议由核心表达预算的增量语义，以免不同 adapter 重复实现。

## 7. 验收门槛

### 7.1 严格 parity

对上述真实 Store 和固定 query：

- source digest 必须保持
  `137e621b1cbde0961feac2c7d06658bc9caae98770dd1c07ff321df345e8a1d2`；
- items = 52；
- spans = 52；
- API Evidence tokens = 99,962；
- Evidence 每个公开字段逐项相等；
- 顺序逐项相等。

对现有 Mneme4 fixtures 和测试集，所有 Evidence digest 与 0.9.1 一致。

### 7.2 性能

真实极端查询应满足：

- 已接纳 item 不再随每个后续候选重复 tokenize；
- 累计 item tokenization 次数从 131,010 降到不超过候选 item 数量级；
- budget measure 阶段目标不超过 5 秒；
- Search 总耗时目标不高于 0.8.3-compatible 路径的 1.10 倍；
- 峰值 RSS 不得相对 0.9.1 基线上升超过 5%。

总耗时应至少运行三次，并分别报告冷读与热页结果；不能用不同 page-cache 状态的单次数字
替代配对结论。

### 7.3 必需测试

至少覆盖：

1. 预算刚好容纳完整 item；
2. 当前 item 超预算、后续较短 item 能被接纳；
3. 多个超大 item 连续跳过；
4. `topn` 先于候选耗尽；
5. budget 先满但仍需检查后续候选；
6. 空结果和 `topn <= 0`；
7. additive 快速路径与 tuple-level fallback 的 Evidence parity；
8. 非 additive 自定义 measure 仍走兼容路径；
9. API 最终序列化内容的 token 数不超过 limit；
10. 长历史 2,500-source 回归测试验证计量调用复杂度。

## 8. 0.9.1 能力边界说明

当前 `mneme-api` 显式传入 `scope_owner="user"`。`EvidenceComposer` 在 scope owner 存在时
直接返回 `ScopedComposer` 结果，因此不会进入 0.9.1 新增的 multi-party、40-source
budget-conditioned cascade。

这意味着：

- 当前比赛 API 中，0.9.1 的新增 cascade 相比 0.9.0 没有行为变化；
- 真实 query 上 0.9.0 与 0.9.1 source digest 完全一致；
- 这不是本性能需求中的 bug；
- 不应通过移除 `scope_owner` 或伪造 participant identity 来启用 cascade；
- 如需把 cascade 扩展到 scoped store，应作为独立算法变更重新做 source、token、Reader 和
  AML proxy 门禁。

## 9. 发布前门禁

建议修复完成后按以下顺序处理：

1. 核心单元测试和 parity fixtures 全部通过；
2. 真实 1,112-history Store 完成三次配对性能验证；
3. `mneme-api` 兼容测试全部通过；
4. 用冻结的 Qwen Reader 与 MiniMax Judge 对 0.8.3 和候选版本做相同输入的配对离线评测；
5. 重点观察 C、D、E、Streaming.online proxy，并要求 A、G、H 不出现实质退化；
6. 通过后发布新的 patch 版本，再由 API 固定依赖版本；
7. 第二次 Full 从 Add 开始固定同一版本，运行期间不再升级。

## 10. 当前判断

Mneme4 scoped composition 是合理的下一次 Full 质量候选，其 held-out 结果与 AML 的时间
演化、更新/遗忘和个性化薄弱项有一定对应关系。不过 100K MemOps 已饱和，论文也没有直接
证明 Answer/Judge 分数提高。因此应先修复当前重复 tokenization，再做冻结 Reader/Judge
门禁，不能仅凭 reader-free Recall 直接预测总分提升。

## 11. 0.9.2 实现与验收结果

`mnemekit 0.9.2` 为 `EvidenceBudget` 增加显式的单 item 计量能力。只有调用方提供
`item_measure` 时，`SourceEvidenceProjector` 才维护单次 Search 生命周期内的 running
total；原 tuple-level `measure` 继续作为非 additive 调用方的兼容路径。API 的单 item
计量复用 `EvidenceFormatter.item()` 的最终渲染文本。

同一 Store、同一 capture 5 私有 query 的配对结果如下：

| 路径 | Search 耗时 | 计量次数 | 累计 item visits | 计量耗时 | 峰值 RSS |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.9.1 tuple fallback，热页 | 158.547 s | 2,500 | 131,010 | 54.813 s | 761.8 MiB |
| 0.9.2 additive，首次运行 | 116.276 s | 2,500 | 2,500 | 1.138 s | 760.0 MiB |
| 0.9.2 additive，热页 1 | 4.836 s | 2,500 | 2,500 | 1.106 s | 763.0 MiB* |
| 0.9.2 additive，热页 2 | 4.605 s | 2,500 | 2,500 | 1.086 s | 764.4 MiB* |

星号 RSS 是同一进程多次运行后的累计 high-water mark。共享机器上没有清空系统 page
cache；“首次运行”表示本次新进程的首遍查询，两个热页结果用于区分缓存状态，不能解释为
强制冷盘数字。

四次运行均返回 52 items、52 spans 和 99,962 Evidence tokens。0.9.2 与 tuple fallback
的每个公开 Evidence 字段及顺序逐项相等，canonical Evidence digest 均为
`f3962a0eda6f618fd5fb1a50b93d050ae610a5cc54a88ed168ed6502f4034066`；source digest 均为
冻结值 `137e621b1cbde0961feac2c7d06658bc9caae98770dd1c07ff321df345e8a1d2`。

因此预算计量阶段低于 5 秒，首次运行低于 0.8.3-compatible 118.793 秒，也低于其 1.10
倍门槛 130.672 秒。核心 318 tests + 4 subtests、API 6 tests、发行包检查与独立安装均通过。
由于 Reader 输入逐字段、逐顺序完全相同，本性能补丁不重复运行 Reader/Judge。

发布落点：核心 tag `v0.9.2`，commit `a8a706acbfcc4cdc516f0066e005eaf28f2ebb45`；
API 固定依赖 commit `7d84378`。
