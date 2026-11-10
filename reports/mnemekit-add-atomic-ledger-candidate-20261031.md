# Mneme Add 原子 Ledger 候选实现与验收说明

日期：2026-10-31\
状态：核心已作为 `mnemekit 0.10.2` 冻结发布；API 集成冻结为 `mneme-api 0.3.1`\
基线：`mneme-api 0.3.0` + `mnemekit 0.10.1`

发布边界：0.10.2 接受的是原子性、Evidence parity 和数据库提交边界减少，不把本地
`3.5%` 吞吐提升表述为生产性能硬门通过。1.57 GiB 同盘配对仍未执行，后续若运行只属于
部署性能验证，不改变本次冻结的检索或论文版本。

## 1. 候选结论

候选实现把新请求的幂等 ledger 放入 Mneme Store，使 request ID、payload hash 与记忆、
posting、图状态在同一个 SQLite transaction 中提交。新路径不再执行 API request DB 的
`pending commit` 和 `done commit`。已有用户目录的后续新 Add 从三个持久化边界降为一个；
fresh user 的首次 Add 仍包含用户 state 初始化与核心原子 Add 两个边界。

`requests.sqlite3` 暂时保留，只承担：

- 旧请求的幂等和冲突判断；
- 升级前遗留 `done=0` 请求的确定性重建；
- 当前 generation 指针。

检索、source ID、timestamp、activation、Evidence projection 和排序没有修改。
无显式 timestamp 时，API 在 Store open 前捕获 `received`，并把同一个值用于 ledger 与全部
缺省消息时间，保持旧路径 Evidence 时间戳语义。

## 2. 接口与数据布局

Core 新增：

```python
Memory.remember_idempotent(
    request_id: str,
    payload_hash: str,
    received: float,
    items: list[RememberInput],
) -> str
```

返回值为 `stored`、`duplicate` 或 `conflict`。`stored` 只会在 ledger 和全部记忆状态已经由
同一个 transaction 提交后返回。

Store 首次执行原子 Add 时，在该 transaction 内惰性创建：

```sql
CREATE TABLE request_ledger (
    id TEXT PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    received REAL NOT NULL
)
```

惰性创建避免 Search 或普通只读打开旧 Store 时发生 schema 写入，也不要求改变现有 schema
版本。ledger 只保存 SHA-256 payload hash，不保存评测原文。

## 3. 崩溃状态机

| 故障位置 | 可见状态 | 重启与重试结果 |
|---|---|---|
| Store transaction 前 | 无 ledger、无新记忆 | 重试正常写入 |
| linguistic/index 更新中 | transaction 回滚 | 无部分 Evidence，重试正常写入 |
| ObjectStore flush 后、COMMIT 前 | ledger、对象与索引全部回滚 | 重试正常写入 |
| COMMIT 中失败 | SQLite 恢复为提交前或完整提交 | 前者重写，后者判定 duplicate |
| COMMIT 后、HTTP 200 前 | ledger 与记忆均已存在 | 重试判定 duplicate，不重复写入 |
| 相同 ID、不同 payload | 不修改 Store | 返回 conflict |

不存在“ledger 完成但记忆缺失”或“记忆完成但 ledger 缺失”的跨库窗口。

升级前的旧 pending 仍先按原有逻辑重建 generation，完成后才允许新原子 Add。部署时不得让
旧写路径和新写路径混跑；升级需要停止旧 worker 后整体切换。回滚代码时必须同时回滚到升级
前 Store 副本，因为旧 API 不认识 Store 内的新 ledger。

## 4. 可观测性

设置 `MNEME_ADD_METRICS_PATH=/absolute/path/add.jsonl` 后，API 输出脱敏 JSONL。默认关闭，
不会给正式 Add 增加指标文件 I/O。字段包括：

- semaphore 与用户锁等待；
- request DB open/schema/query/close；
- 旧路径 pending/done commit（仅兼容路径）；
- Store open、remember、GC；
- core analyze、index update、evolution、ObjectStore flush、Store commit。

记录只含 user hash、message count、错误类型和耗时，不含 request payload、query、Evidence、
session ID 或密钥。

## 5. 本地机制测量

在同一台本地磁盘、相同 fresh Store、相同 5 次单消息 Add 上，以 `strace -f -c` 统计：

| 路径 | fsync | pwrite64 | fcntl |
|---|---:|---:|---:|
| 0.10.1 三事务路径 | 76 | 751 | 1,138 |
| 原子 ledger 候选 | 36 | 661 | 1,028 |
| 变化 | -52.6% | -12.0% | -9.7% |

该测量包含初始化固定成本，因此只用于确认持久化边界确实减少，不作为生产吞吐结论。本地
phase profile 中提交耗时很小，而生产普通云盘的 I/O wait 为 64%–77%；最终性能必须由 API
方在同盘、同 Store 副本、同回放上三轮配对测量。

补充的三轮、每轮 25 次单消息 Add 微基准如下：

| 路径 | 三轮吞吐（Add/min） | 三轮 P50（ms） | 三轮 P95（ms） |
|---|---|---|---|
| 0.10.1 三事务路径 | 1098 / 1775 / 1780 | 34.45 / 33.35 / 33.14 | 47.04 / 36.28 / 39.55 |
| 原子 ledger 候选 | 1272 / 1836 / 1843 | 32.92 / 32.69 / 32.12 | 39.24 / 33.61 / 33.75 |

本地热轮吞吐约提高 3.5%，三轮中位 P95 约降低 14.7%。由于本地提交本来就低于 1 ms，收益
远小于 I/O 饱和云盘的预期；这些数字同样不能替代生产门禁。

## 6. 已完成验证

- Core 全套：375 tests + 4 subtests passed；
- Core Store + evolution 定向测试：25 tests passed；
- API 接旧 mnemekit 兼容路径：9 passed，2 atomic-only tests skipped；
- API 接本地原子 Core：11 tests passed；
- 同请求四进程并发 Add：无重复 Evidence；
- 同 ID 同 payload：duplicate；
- 同 ID 不同 payload：conflict；
- ledger 写入前故障：记忆与 ledger 同时回滚；
- ObjectStore flush 后故障：记忆与 ledger 同时回滚；
- Core commit 后模拟响应丢失：重试不重复；
- 0.10.1 遗留 pending 升级恢复后继续原子 Add：旧、新 Evidence 各出现一次；
- 人为延迟 Store open 后，缺省 timestamp 仍取 open 前时间，显式 timestamp 严格不变；
- 原路径与原子路径 Evidence 公开结构和顺序严格相等。

## 7. API 方验收重点

API 方仍需完成：

1. 在脱敏 1.57 GiB Store 副本上做逐 Add Evidence digest parity；
2. 对冷页、热页分别三轮比较 Add P50/P95/P99、吞吐、每 Add sync 与写入 bytes；
3. 比较 Search P50/P95/P99、RSS、Store 大小与 I/O PSI；
4. 覆盖同用户 16 并发、不同用户 16 并发、4 worker 混合 Add/Search；
5. 在维护窗口旁路升级，禁止当前 Full 热切换；
6. 验收通过后再确定 mnemekit 与 mneme-api 的发布版本并更新依赖 pin。

生产硬门仍按原需求执行：吞吐至少 1.5 倍、目标 25 Add/分钟、Add P95 至少降低 35%、
Search 回退不超过 5%、RSS 与磁盘不增加超过 10%，且不得出现 5xx、锁超时或数据库损坏。
