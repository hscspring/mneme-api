# Mneme Add 原子 Ledger：API 侧阶段验收

日期：2026-10-31\
候选：已发布的 `mnemekit 0.10.2` atomic request ledger\
基线：`mneme-api 0.3.0` + `mnemekit 0.10.1`\
最终结论：时间戳 parity blocker 已修复；核心与 API 集成已冻结发布，大 Store 性能门仍未执行

本文件以下第 1--7 节保留 2026-10-31 阶段验收原文。后续实现已改为在 Store open 前捕获
`received`，并由同一个值生成 ledger 与缺省消息时间；对应回归测试及严格 Evidence parity
均已通过。发布接受的是等价原子事务与 I/O 边界减少，不宣称达到原文中的生产性能硬门。

## 1. 当前结论

候选把 request ledger、记忆、索引和图状态放入同一个 Mneme Store transaction，消除了
新请求在 API request DB 中的 pending/done 两次提交。该方向与 I/O 优化需求一致，已有
故障注入和多进程测试覆盖了主要原子性边界。

API 侧独立复核结果：

- `PYTHONPATH=. .venv/bin/pytest -q`：Core 375 passed，4 subtests passed；
- `PYTHONPATH=/mnt/sv0/sean/research/Mneme .venv/bin/pytest -q`：API 10 passed；
- `git diff --check`：Core 与 API 均无 whitespace error；
- 当前生产 Full 未加载候选代码，继续固定 0.10.1。

候选目前不能发布或部署，原因有两个：

1. API 新路径改变了无显式 timestamp 消息的 `received` 取值时点；
2. 生产性能硬门尚未完成，本地热轮仅证明机制有效，未达到发布所需的实机证据。

## 2. P0 blocker：默认时间戳取值时点发生变化

旧路径的顺序是：

1. 在 `requests.sqlite3` 插入 pending 时执行 `time.time()`；
2. 提交 pending；
3. 打开 Mneme Store；
4. 用 pending 记录中的 `received` 生成缺省消息时间戳。

候选新路径的顺序是：

1. 打开 Mneme Store；
2. 调用 `_remember_idempotent(..., time.time(), ...)`；
3. 用该时间生成缺省消息时间戳。

因此，当输入消息没有显式 `timestamp` 时，候选的 source timestamp 会比旧路径晚一个
`store_open` 时长。短 Store 上差异可能很小；真实长 Store 冷开时可能达到秒级。timestamp
属于比赛返回的公开 Evidence 字段，也可能参与稳定排序和时间语义，不能把它视为纯内部差异。

修复要求：

- 在进入 `_memory()` 之前捕获一次 `received`；
- 原子路径把该值同时用于 ledger 和所有无显式 timestamp 的 `RememberInput`；
- legacy fallback 保持原行为；
- duplicate/conflict 不得覆盖 ledger 中第一次提交的 `received`。

必须新增一个最小回归测试：让 Store open 人为产生可观察延迟，对同一无 timestamp 请求验证
候选使用的是 open 前的时间；同时确认带显式 timestamp 的请求不受影响。

## 3. 提交次数表述需要收窄

“Add 从三次持久化提交降为一次原子提交”对已有用户目录中的后续新请求成立，但对每个新
用户的第一次 Add 不完全成立。

第一次访问用户目录时，API 仍会：

- 创建 `requests.sqlite3`；
- 创建 `requests/state` 表；
- 写入 generation 并提交；
- 随后执行 Mneme atomic ledger transaction。

所以首次 Add 至少还有“用户状态初始化 + 核心原子 Add”两个持久化边界。这个兼容成本可以
接受，但发布说明和性能报告应明确区分：

- fresh user 首次 Add；
- existing user 后续 Add；
- legacy pending 恢复；
- duplicate retry。

AML 有大量独立历史，fresh-user 成本不能只用单用户热轮吞吐掩盖。

## 4. 性能门尚未通过

现有机制数据：

- `fsync`：76 → 36，下降 52.6%；
- `pwrite64`：751 → 661，下降 12.0%；
- 本地热轮吞吐提升约 3.5%；
- 三轮中位 P95 降低约 14.7%。

这些结果证明事务边界确实减少，但当前发布硬门仍是：

- 持续吞吐至少提升 1.5 倍；
- 目标达到 25 Add/分钟；
- Add P95 至少降低 35%；
- Search 回退不超过 5%；
- RSS 与磁盘不增加超过 10%。

普通本地盘上提交成本很低，不能推断 I/O 饱和云盘收益。候选可能在生产盘上获得更大提升，
但在配对实测完成前只能判为“性能假设成立、生产收益未知”。

## 5. 大 Store 门禁资产与执行边界

现有真实形态资产：

```text
/mnt/sv0/sean/research/Mneme/.runtime/full-store-1112-20261010/
```

已核对规模：

- 目录总量约 1.6 GiB；
- `store.sqlite3`：1,687,867,392 bytes；
- `requests.sqlite3`：19,619,840 bytes；
- 包含保存的脱敏 query 与既有 profile，不需要重新抽取原始 Full 数据。

完整配对门禁需要至少两个 Store 工作副本，并分别执行基线/候选、冷页/热页和三轮测量，预计
产生约 3.2–6.4 GiB 工作副本和数十 GiB 累计读写。它属于大规模 I/O 操作，必须单独授权后
才能启动。

当前生产云盘的 I/O wait 为 64%–77%，且 Full 正常运行。不得在同一云盘同时启动该门禁；
同盘验证只能等待平台任务明确中断或 Full 完成。现在可以先在本机副本完成语义 parity，
但本机性能数字不能替代生产盘结果。

## 6. 下一轮验收顺序

1. 修复 `received` 捕获时点并增加回归测试；
2. 重跑 Core 375 + 4 subtests 与 API 10 tests；
3. 对 1.57 GiB Store 副本执行升级前后 Search Evidence 严格 parity；
4. 追加一组代表性 Add，比较默认 timestamp、ledger、Store 和重启结果；
5. 本机完成三轮冷/热 Add 与 Search 基准；
6. 等当前 Full 中断或结束后，在相同云盘做受控配对；
7. 达到硬门后再发布 mnemekit/API 版本；
8. 新版本只用于后续独立部署，不热切换当前运行中的 Full。

## 7. GO/NO-GO

- 原子事务设计：GO；
- 幂等、冲突、回滚和多进程机制：GO；
- 当前 Evidence 严格 parity：NO-GO，待修复默认 timestamp；
- 本地功能测试：GO；
- 1.57 GiB Store 门禁：未执行；
- 同云盘性能门：未执行；
- 发布：NO-GO；
- 当前 Full 部署：保持 0.10.1，不变更。
