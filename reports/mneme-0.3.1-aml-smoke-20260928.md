# Mneme 0.3.1 Agent Memory Leaderboard Smoke 报告

## 结论

Mneme 0.3.1 的 `Memory.search_evidence()` 已经通过 Agent Memory Leaderboard 文本赛道 Smoke。Add、Search、统一 Answer 和 Eval 四个阶段全部成功，默认 TAG projection 返回的 EvidenceItem 及多 span 内容符合平台契约。

Smoke 综合分为 **51.17**。该结果只基于 46 个 Smoke 样本，用于验证接入和初步定位问题，不能与 Full 或公开榜单分数直接比较。

## 评测信息

| 项目 | 值 |
|---|---:|
| 评测日期 | 2026-09-28 |
| 赛道 | Textual |
| 模式 | Smoke |
| 状态 | Succeeded |
| 评测任务 | `teval_2ec303ce50b8cf5d` |
| Mneme | `mnemekit==0.3.1` |
| API | `mneme-api==0.1.3` |
| API commit | `13dfbeb` |
| Top K | 100 |
| Add 并发度 | 16 |
| Search 并发度 | 16 |
| 开始时间 | 2026-09-28 07:58:54 UTC |
| 完成时间 | 2026-09-28 08:13:16 UTC |
| 总耗时 | 14 分 22 秒 |
| 完成样本 | 46/46 |

其中 Textual 分支 18/18，Streaming 分支 28/28。本次没有复用 Add cache。

## 接口路径

API 在 Search 时直接调用：

```python
items = memory.search_evidence(query, topn=top_k)
```

没有在 API 层实现额外的召回、排序、投影或去重。本次使用 Mneme 0.3.1 的默认 TAG projection：

- 一个 tag 投影为一个 EvidenceItem。
- `top_k` 在 evidence projection 之后执行，限制的是 item 数量。
- 每个 item 包含核心返回的全部 spans。
- API 将每个 span 的 `source_id`、`role`、`timestamp` 和 `text` 写入 `content`。
- API 保留 Mneme 的 item 排序，不返回额外 score。
- 本次未启用 `TAG_DEDUP`。

平台完整接受了这一返回形式，因此可以确认：AML 不要求 Search 结果必须是单个原始 turn，核心 EvidenceItem 可以作为一条记忆证据，且一条证据可以包含多个 span。

## 结果

| 维度 | 分数 | Smoke 样本数 |
|---|---:|---:|
| Overall | 51.17 | 46 |
| A 显式事实召回 | 60.00 | 5 |
| B 关系与多跳推理 | 33.33 | 3 |
| C 时间与事件序列 | 45.00 | 4 |
| D 记忆治理 | 20.00 | 6 |
| E 个性化与关怀 | 100.00 | 2 |
| G 上下文学习与执行 | 30.00 | 4 |
| H 认识论安全与隐私 | 50.00 | 2 |
| Streaming | 59.38 | 28 |

Smoke 中 E 只有 2 个样本，B 只有 3 个样本，其他非 Streaming 维度也只有 2–6 个样本。这些分数适合形成检查假设，不适合用来确定稳定的能力排序。

## 对 Mneme 核心的观察

1. **Evidence 边界已经被真实端到端链路验证。** Add 后的数据可以通过 `search_evidence()` 投影为多 span EvidenceItem，并被平台的 Answer 模型正常消费。

2. **TAG 聚合对个性化和 Streaming 有初步正面信号。** E 和 Streaming 是本次相对较强的结果，但样本量不足以确认稳定优势。

3. **记忆治理是最明显的检查方向。** D 为 20。建议检查同一 tag 下的旧事实、更新事实和冲突事实如何共存，以及时间和当前有效状态是否会在证据中被充分表达。

4. **多跳证据的组织方式需要检查。** B 为 33.33。默认 TAG 以 query tag 为 item 边界，关联链上的不同事实可能被分散在不同 item，或因某个关键 tag 未出现于 query 而没有进入候选。这是需要通过具体失败样本验证的假设。

5. **Top-K 不能限制 span 总量。** 一个高频 tag 可以带回大量 spans。虽然 Search 最多返回 100 个 items，单个 item 的内容仍可以很长。AML 的 Answer 输入总预算为 117,760 tokens，超出后按 Search 顺序保留前缀。因此高频 tag 的 span 排序和证据密度可能直接影响 Full。

6. **规则与流程执行需要单独验证。** G 为 30。可优先检查精确的否定词、条件、顺序和例外条款在 tag 抽取和 span 投影后是否保持完整。

## Full 前建议

建议在首次 Full 前先做三项最小验证：

1. 用长历史统计 Search 返回的 item 数、span 数和 token 总量，特别关注高频 tag。
2. 对事实更新、反事实和时间顺序构造小型样本，比较 `TAG` 与 `TAG_DEDUP` 的证据质量。
3. 对多跳问题检查必需的中间证据是否都进入前排 EvidenceItem。

这次 Smoke 已经证明当前核心接口可以参加正式评测。下一阶段的重点应放在 evidence 的选择与排序质量，而不是 API 契约。

## 限制

- Smoke 不公开具体问题、金标答案、单题检索结果或失败原因，本报告无法将分项失分归因到某一个核心机制。
- 分项样本少，一个样本就可以显著改变分数。
- Smoke 与 Full 的数据规模不同，本次耗时不能线性外推为 Full 耗时。
- 本次未启动 Full，Full 额度仍为 0/2。
