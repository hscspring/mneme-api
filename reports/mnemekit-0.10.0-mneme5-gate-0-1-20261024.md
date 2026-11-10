# mnemekit 0.10.0 Mneme5 路线 A Gate 0–1 冻结记录

日期：2026-10-24\
核心 commit：`76715e6efcdb28010a3d600c0cee4e9ea8293d05`\
核心版本：`mnemekit==0.10.0`\
API 候选：`mneme-api==0.3.0`\
API commit：`ebd20e7e8b3d98f1cdc58f484fe17a26c7578165`\
API fallback commit：`022a2a558cc772fb632e8fde6456113958916b99`，main 已恢复
`mnemekit==0.9.2`\
状态：Gate 0–2 与 legacy reader-free 门已通过；比赛部署仍待 Answer、完整性能、发布与 Smoke

> 2026-10-24 终态更正：本文末尾最初的 Gate 2 NO-GO 使用了错误的“实际返回数量必须
> 完全相同”口径。AML 与论文公平比较要求相同 Top-K/token **上限**，不要求 baseline
> underfill 时两个检索器返回等量结果。所有数量不一致 cell 的 headline Recall 均为 tie，
> 因此 Gate 2 最终为 PASS。论文证据终态 commit 为 `4fd74cf`。

## 冻结方法

路线 A 只实现 bounded forward successor activation：

- 一次 `remember_many()` / API Add 批次形成一个私有 evolution episode；
- source 的 event、exchange、role、timestamp、ID 与原文完全不变；
- episode packet 只使用 user source；
- `char_wb` 4-gram，lowercase，sublinear TF，无 IDF；
- relation threshold `0.20`；
- top-1 与 top-2 margin `0.05`；
- 同一 per-user Store 内严格从早到晚，只保留一个 predecessor；
- query 只允许 activation 最强的 10 个 episode 作为 seed；
- forward activation `0.25`；
- 原 source 全部保留，不做 active-head、stale suppression 或生成式改写。

API 每个 `user_id` 使用独立 Store，因此 relation 候选不会跨 user。没有 relation 或 top-10
seed 未命中时，SuccessorActivation 原样返回 0.9.2 activation。

核心 tokenizer/实现文件 SHA256：
`f095467de1543e177fce0c4caf5a209dec11b532f7e23a87e74b771a2e5c1d34`。

## Development 与 tuning 结果

### STALE development

| 指标 | Top-10 | Top-20 | Top-40 |
|---|---:|---:|---:|
| Latest Recall baseline | 54.58 | 70.00 | 81.94 |
| Latest Recall candidate | 58.75 | 73.75 | 83.61 |
| Latest Recall Δ | +4.17 | +3.75 | +1.67 |
| Stale exposure Δ | -0.14 | 0.00 | 0.00 |
| paired 95% interval | [+2.64,+5.83] | [+2.36,+5.28] | [+0.56,+2.78] |

Relation 为 75 accepted / 73 correct，precision `97.33%`。该 split 已参与开发，不能
替代 sealed held-out。

### Memora tuning

15 conversations、300 questions：

| 指标 | Top-10 | Top-20 | Top-40 |
|---|---:|---:|---:|
| Current Recall Δ | -0.28 | -0.13 | -0.07 |
| Stale exposure Δ | 0.00 | -0.08 | -0.01 |

三档 current recall 均在 `-1pp` 内，stale exposure 不增加。此前全历史 TF-IDF 方法的
Top-10 `-8.23pp` 风险已被消除，但 validation 和 held-out 尚未打开。

## Artifact 与构建

| Artifact | SHA256 |
|---|---|
| `mneme5-stale-development-production.json` | `05dc751af6f4e1015d55da90bb89c19b292e7eaf40a101d031b465537fb713d3` |
| `mneme5-stale-development-production-relations.json` | `3d7903a59c22dca0d78835f28c0083f872ca9ef9a213aa196e61cd70eddc6251` |
| `mneme5-memora-tuning-production.json` | `253914507dbcc18dec3d380f9058e3db2957361fb6c167b663978dbff3fb68c0` |
| `mnemekit-0.10.0-py3-none-any.whl` | `32cf37819ae5170118d72baa61e5033298fa53075c2c7d6b686803dee9925e8c` |
| `mnemekit-0.10.0.tar.gz` | `9cd48b922ba0a37053d253dc2f49c9540ac58ef1a6118d6738ee0d1f02d5dec5` |

核心全仓为 `360 passed, 4 subtests passed`。API 使用工作区冻结核心运行，为
`7 passed`。wheel 在隔离 venv 中成功安装并完成 Add/relation/Search smoke。

## 真实 1.57 GiB Store 首轮性能

使用私有保留 Store 的副本，不修改原快照。该 Store 有 2,500 turns、1 个历史 session
event；显式迁移因此保守生成 1 个 legacy episode、0 relation 和 2,500 source mappings。

| 项目 | 结果 |
|---|---:|
| 迁移 wall time | 67.05 s |
| 迁移峰值 RSS | 743,296 KB |
| 迁移 swap | 0 |
| feature postings | 168,979 |
| 数据库追加写 | 约 16 MiB |
| 0.9.2-compatible Search | 111.190 s |
| Mneme5 migrated Search | 106.375 s |
| Search 倍率 | 0.957x |
| Search 峰值 RSS | 957,856 → 965,312 KB |
| Add | 7.732 → 8.418 s，1.089x |

Search 两边均为 52 items、52 spans、99,962 tokens，Evidence digest 都是
`a84ddd7042ceddfa4f7e474c8bc4db27bd4ab736585c74e4c4db8adf53b40d21`。

这些是单次首轮结果，只证明实现没有明显资源灾难，不能替代 Gate 6 要求的三次冷/热页、
100 次 RSS、1K/10K Add P95 和中断迁移恢复。

## 未完成门禁

- STALE sealed held-out；
- Memora validation 与 held-out；
- LoCoMo、LongMemEval-S、BEAM、MemOps、SocialMemBench legacy non-regression；
- Qwen Reader / MiniMax Judge 三次 Answer 非劣；
- Gate 6 完整重复性能；
- PyPI 发布、独立 PyPI 安装、远端稳定性与官方 Smoke。

任一后续门失败都回退 `mnemekit==0.9.2`，不在 sealed 结果之后改方法参数。

## Gate 2 结果：PASS（更正后的最终判定）

冻结后打开 STALE held-out 80 scenarios、240 queries。Latest Recall@10/20/40 为
`+4.17/+3.33/+1.67pp`，Top-20 paired 95% interval 为 `[+0.42,+6.67]pp`；
stale exposure 三档均为 `0.00pp`，relation precision 为 `30/31=96.77%`。

统计与安全指标通过。source-count parity 为 Top-10 `240/240`、Top-20 `238/240`、
Top-40 `224/240`；差异来自 baseline underfill 后 successor 补入候选。18 个 mismatch
cell 的 Latest Recall delta 全部为 0，因此收益不是额外 source 数造成。预冻结的 exact
source-count 条款误把“相同上限”写成“相同实际返回数”，现已纠正。候选在相同 Top-K 与
token 上限下公平比较，Gate 2 最终判定 PASS。

随后完成的五个 legacy population source-budget 与 8K/24K/100K token-budget 回归也均
通过 `-1pp` 非退化门，详见核心仓库 commit `4fd74cf` 与
`paper-5-dependency-directed-revision/legacy-nonregression-result.md`。尚未完成的比赛门为
Memora 外部确认、Qwen Reader / MiniMax Judge Answer gate、完整真实 Store 重复性能、
PyPI/API 正式发布、远端稳定性和官方 Smoke。

Held-out artifact SHA256：

- recall：`3d13c5af73b9b2d6214a5c61346ee13e4137bdc15b2e80c943c89e99c83e47e6`；
- relation：`1060f9ad62222d33930e0f76ead195f2e8e1a1b61f43dba1ee9e5bd648050e2a`。
