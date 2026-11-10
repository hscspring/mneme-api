# Mneme Add 持久化与 I/O 性能优化需求

日期：2026-10-31\
优先级：下一次生产部署前的高优先级工程优化\
当前基线：`mneme-api 0.3.0` + `mnemekit 0.10.1`\
性质：等价性能优化，不改变 ALG-DDR-1、Evidence 语义或 AML 接口行为

## 1. 结论

当前 AML Full 的 Add 阶段已经稳定运行，但生产监控表明主要瓶颈不是 CPU、内存或
SQLite 单库写锁，而是四个进程同时对同一块云盘执行小事务、索引更新和同步持久化造成的
I/O 等待。

在 4 vCPU、8 GiB RAM、4 个 Uvicorn worker 的生产机上：

- Add 持续吞吐约 13–14 次/分钟；
- CPU load average 约 4.7–5.0，但 CPU user + system 通常只有约 8%–20%；
- `vmstat` 的 I/O wait 为 64%–77%；
- `/proc/pressure/io` 的 `full avg60` 为 72.81%，`full avg300` 为 72.89%；
- 系统仍有约 4.4 GiB available memory，Swap 使用为 0；
- 数据盘仍有约 61 GiB 可用空间；
- 四个业务 worker 的 RSS 合计约 3.0 GiB；
- 同期 Add/Search 没有业务 4xx/5xx 或 traceback。

因此当前性能边界是持久化路径和底层块设备，而不是计算资源不足。增加 worker 或 CPU
不会自然解决问题，并可能进一步放大随机写、WAL checkpoint 和 `fsync` 竞争。

本需求要求先量化每次 Add 的事务、同步和写放大，再减少持久化次数和重复数据库生命周期
开销。任何优化都必须保留同步 Add、立即可检索、请求幂等、崩溃恢复和 Evidence parity。

## 2. 当前实现边界

### 2.1 API 并发与用户隔离

当前生产运行四个 Uvicorn worker。每个进程中的 `MemoryService` 默认
`max_concurrency=1`，所以整机最多并行执行四个业务请求。

每个 `user_id` 被映射到独立目录：

```text
<root>/<sha256(user_id)>/
```

每个用户目录拥有独立的：

- `requests.sqlite3`；
- Mneme Store；
- 跨进程 `fcntl.flock(LOCK_EX)` 用户锁。

用户锁覆盖完整 Add/Search 操作。同一用户严格串行，不同用户可以由四个 worker 并行。
因此这不是“所有请求争抢同一个 SQLite writer lock”的结构。当前更可能是多个独立数据库
同时争用同一块云盘的 IOPS 和同步写延迟。

### 2.2 单次 Add 的持久化路径

当前 API Add 的主要顺序为：

1. 获取用户文件锁；
2. 打开 `requests.sqlite3`；
3. 检查 `request_id` 和 payload；
4. 插入 `done=0` 的请求记录并提交；
5. 打开 Mneme Store；
6. 执行 `memory.remember()`，更新对象、posting、集合和图状态并提交；
7. 更新请求记录为 `done=1` 并提交；
8. 关闭数据库和 Store，释放用户锁；
9. 执行一次显式 `gc.collect()`。

Mneme Store 当前使用：

- `journal_mode=WAL`；
- `synchronous=NORMAL`；
- 顶层事务使用 `BEGIN IMMEDIATE`；
- 提交前刷新 ObjectStore。

从代码结构可以确认单次成功 Add 至少跨越三个事务边界，但当前尚未用系统调用 profile
精确测量实际 `fdatasync/fsync` 次数、写入字节数、脏页数和 checkpoint 成本。不能在没有
测量的情况下把所有 I/O wait 简化为 SQLite 锁竞争。

### 2.3 当前方案的必要语义

`requests.sqlite3` 不是无意义的重复日志。它承担：

- 相同 `request_id` 重试的幂等判断；
- 相同 ID、不同 payload 的冲突检测；
- Add 中途崩溃后的 Store 重建；
- 只有完整写入后才把请求标记为 `done=1`。

直接删除该数据库或把 `done` 更新改成异步，会破坏 AML 同步 Add 合同和断点续跑安全性。

## 3. 优化目标

### 3.1 主目标

在保持完整语义的前提下，降低每次 Add 的：

- durable transaction 数量；
- `fsync/fdatasync` 次数；
- SQLite page/WAL 写放大；
- 数据库重复打开、schema 检查和状态加载成本；
- 多 worker 对同一块云盘的随机写竞争。

### 3.2 生产目标

在与当前生产相同的 4 vCPU、8 GiB RAM、4 worker、同类云盘和同一回放流量下：

- 必须：连续 60 分钟 Add 吞吐至少达到当前基线的 1.5 倍；
- 目标：达到至少 25 Add/分钟，约为当前基线的 1.8 倍；
- 必须：Add P95 延迟相对基线降低至少 35%；
- 必须：单位 Add 的同步持久化次数和写入字节数有可复核的下降；
- 必须：Search P50/P95 不回退超过 5%；
- 必须：峰值 RSS 不增加超过 10%；
- 必须：Store 磁盘占用不增加超过 10%；
- 必须：压力测试中不使用 Swap，不出现业务 5xx、数据库锁超时或损坏。

I/O PSI 和 I/O wait 必须报告，但不单独作为硬门。吞吐提高时磁盘利用率可能保持较高，真正
需要比较的是每个成功 Add 的同步次数、写入量、延迟和完成吞吐。

## 4. 必须保持的行为

优化不得改变以下行为：

1. Add 只有在记忆已持久化且后续 Search 可立即读取时才返回 HTTP 200。
2. 相同 `request_id` 和相同 payload 的重复 Add 不产生重复记忆。
3. 相同 `request_id` 和不同 payload 继续返回冲突。
4. 进程在任意持久化边界崩溃后，重启必须得到“完整提交”或“可安全重放”状态。
5. 不允许出现请求账本显示完成、Mneme Store 实际缺失的状态。
6. 不允许出现 Mneme Store 已重复写入、请求账本却无法识别重试的状态。
7. `user_id` 隔离、`session_id`、source ID、role、timestamp 和原文完全不变。
8. Mneme activation、successor recall、排序、Top-K 和 Evidence projection 完全不变。
9. 同一冻结 Store 和 query 的 Evidence 公开字段、顺序和 digest 严格一致。
10. 现有 schema 的只读打开、显式迁移、事务内 Search 和 rollback 语义保持不变。
11. 不允许用 `synchronous=OFF`、不落盘返回成功或丢弃索引更新换取性能。
12. 不允许加入数据集名称、题目特判或 AML 专用内容规则。

## 5. 第一阶段：只做可观测性

实施优化前必须先建立基线，至少记录以下分段耗时：

- 等待全局业务 semaphore；
- 等待用户 `flock`；
- 打开 request DB；
- 幂等查询；
- pending request 写入与提交；
- 打开 Mneme Store；
- schema/metadata 加载；
- linguistic extraction；
- activation 和索引更新；
- ObjectStore flush；
- Mneme transaction commit；
- request `done` 更新与提交；
- 关闭连接；
- `gc.collect()`。

同时用 `strace -c/-T`、eBPF 或等价工具，对代表性 Add 测量：

- `fsync`、`fdatasync`、`pwrite64`、`write`、`fcntl` 次数和耗时；
- 单次 Add 写入字节数；
- WAL 文件增长和 checkpoint；
- 用户锁等待与 SQLite transaction 等待；
- 冷 Store、热 Store、短历史和长历史的差异。

采样不得记录评测原文、query、Evidence 文本或任何密钥。生产 Full 运行期间只允许低开销
指标；系统调用级 profile 应在一致性快照或合成回放上进行。

## 6. 建议的优化顺序

### 6.1 P0：减少双层事务与重复同步

首选方向是让请求幂等状态和 Mneme 记忆状态共享一个可证明的原子提交边界。

可选设计包括：

1. 在 Mneme Store 中增加通用的 request ledger，由同一个 transaction 同时写入
   request payload hash、完成状态和记忆变更；
2. 提供核心级 `remember_idempotent()` 或 transaction extension hook，让 API 的 ledger
   写入参加 Mneme 原事务；
3. 使用一个追加式 durable journal 作为唯一事实源，Mneme 索引能够按确定 ID 幂等重放；
4. 如果必须保留双库，证明能否安全合并 API 的 pending/done 两次提交，并给出严格的崩溃
   状态机。

目标是把“API pending commit + core commit + API done commit”从至少三个持久化边界减少到
一个；若一个边界暂时不可实现，第一版硬上限应为两个。

不能仅通过删除 pending 状态实现合并。设计必须逐项解释进程在每个边界被强制中止后的恢复
结果。

### 6.2 P1：减少连接和 Store 生命周期开销

当前每次操作都会重新打开 request DB 和 Mneme Store。应测量并评估有界复用：

- 每进程维护有容量上限的 LRU user handle；
- 复用 SQLite connection、prepared statement 和只读 metadata；
- 设置 idle TTL，避免评测中上千用户导致连接和文件描述符无限增长；
- 退出时正常关闭，异常退出依赖 SQLite 恢复；
- schema generation 变化时立即失效。

多进程缓存存在明确风险：同一用户的下一次请求可能落到另一 worker，后者缓存的 Store 状态
可能过期。除非增加跨进程 generation 校验、可靠失效或按 user 做 sticky routing，否则不得
直接缓存可变 Mneme 对象。连接复用必须先证明跨进程一致性。

### 6.3 P2：降低 SQLite 写放大

在事务结构优化后再评估 SQLite 参数和表布局：

- 统计每类 Add 更新的 page 数和 WAL bytes；
- 评估 page size、cache size、`mmap_size` 和 `wal_autocheckpoint`；
- 避免每次请求重复执行无必要的 schema DDL/check；
- 将同一次 Add 的 posting、object、set 和 metadata 更新保持在一个 transaction；
- 批量执行相同表的写入，减少 statement 和 B-tree 往返；
- 检查索引是否造成重复维护或低选择性写放大；
- checkpoint 应有明确策略，避免多个用户数据库同时触发尖峰。

Mneme core 已使用 WAL + NORMAL。任何进一步降低同步等级的方案必须通过掉电等价测试；
`OFF` 或“只依赖进程退出时 flush”不允许进入候选。

### 6.4 P3：评估追加式 Store，但不预设必须替换 SQLite

可以实现独立原型，比较：

- append-only event log；
- 分块 posting；
- 内存或 mmap 热索引；
- 周期性 snapshot/compaction；
- 启动时按日志恢复。

原型必须包含崩溃一致性、幂等、compaction 中断恢复和 Search 冷启动成本，不能只比较顺序
append 的理想吞吐。普通文件仍需要同步落盘；如果每个 Add 创建多个小文件，元数据和
`fsync` 成本可能比 SQLite 更高。

只有在同一回放负载下显著超过优化后的 SQLite，并通过完整 parity 和故障注入，才考虑替换
正式 Store。

### 6.5 P4：部署层兜底

部署层可以使用本地 NVMe 或 provisioned IOPS 磁盘降低延迟，但这只能作为容量方案，不能
替代核心写放大优化。性能报告必须分别给出：

- 当前普通云盘；
- 高 IOPS/NVMe；
- 单 worker 与四 worker；
- 冷启动与稳定运行窗口。

## 7. 必需测试

### 7.1 幂等与冲突

1. 同一请求连续提交两次；
2. 同一请求由两个进程并发提交；
3. 同一 ID、不同 payload；
4. 平台超时后重试；
5. 重启后再次提交已完成请求。

### 7.2 故障注入

至少在以下位置模拟进程异常退出：

1. request ledger 写入前；
2. ledger 写入后、核心事务前；
3. 核心对象写入中；
4. ObjectStore flush 后、COMMIT 前；
5. 核心 COMMIT 后、完成标记前；
6. 完成标记提交期间；
7. WAL checkpoint 期间；
8. schema migration 期间；
9. compaction/snapshot 期间（若引入）。

每个故障点重启后都必须满足：无部分可见状态、无重复 Evidence、原请求可安全重试、不同
payload 仍能检测冲突。

### 7.3 并发

至少覆盖：

- 同一用户 16 个并发 Add；
- 16 个不同用户并发 Add；
- 同一用户 Add/Search 交替；
- 不同用户 Add/Search 混合；
- 4 个独立进程访问相同根目录；
- 长历史用户与短历史用户同时运行，验证无饥饿。

### 7.4 语义 parity

对升级前后的同一请求序列：

- 每个 Add 后执行定向 Search；
- 比较 Evidence item/span 数；
- 比较所有公开字段和顺序；
- 比较 source digest；
- 比较 evolution source 数；
- 比较 8K、24K、100K budget 输出；
- 比较重启前、重启后和迁移后的结果。

### 7.5 性能回放

使用两组数据：

1. 可公开的合成负载，用于持续集成；
2. 本地忽略路径中的脱敏生产形态快照，用于发布门禁。

每组至少报告：

- Add P50/P95/P99；
- 每分钟成功 Add；
- CPU user/system/iowait；
- I/O PSI；
- 每 Add 写入 bytes 和同步次数；
- worker RSS 与整机峰值 RSS；
- Store 大小；
- Search P50/P95/P99；
- 1、2、4 worker 的扩展效率。

基线和候选必须在同一机器、同一磁盘、同一初始 Store 副本和相同 page-cache 口径下运行。
至少重复三轮，分开报告冷读和热页，不得用单次最好结果替代。

## 8. 非目标

本优化不包含：

- 修改 successor activation 或任何召回规则；
- 修改 Evidence 排序、组合、Top-K 或 token budget；
- 调低持久化保证；
- 将同步 Add 偷换成未经平台批准的异步 Add；
- 通过减少写入的记忆内容换取性能；
- 针对 AML 数据集、题型或已知 case 特判；
- 在当前正在运行的 Full 中热切换 Store 实现；
- 单纯增加 worker 并把更高磁盘排队当作优化。

## 9. 交付物

核心实现方应提供：

1. Add 持久化 phase profile；
2. 每次 Add 的事务与同步调用账本；
3. 设计说明和崩溃状态机；
4. 实现与 schema migration；
5. 故障注入、并发和 parity 测试；
6. 同机配对性能报告；
7. 生产升级与回滚步骤；
8. API 适配方需要修改的最小接口说明。

私有评测请求、原始对话、query、Evidence 和密钥不得进入 Git、wheel、sdist 或公开报告。

## 10. 发布门禁与当前 Full

当前 Full 必须继续固定 `mneme-api 0.3.0` 和 `mnemekit 0.10.1`，不得在运行中替换持久化
实现。当前吞吐仍稳定，资源没有进入危险区，继续运行的风险低于中途升级。

新实现只有在以下条件全部通过后才能发布或用于下一次评测：

1. 所有现有核心和 API 测试通过；
2. 新增故障注入和多进程测试通过；
3. 真实形态 Store 的 Evidence parity 严格通过；
4. 达到第 3.2 节的性能门槛；
5. Search、RSS 和磁盘占用无实质回退；
6. wheel/sdist 不包含私有复现材料或报告；
7. 全新环境完成 Add、重试、重启、Search 和迁移 smoke；
8. 生产先以新 Store 副本完成旁路验证，再安排独立维护窗口切换。

当前判断是：SQLite 仍可作为可靠基线，但 API request ledger 与 Mneme Store 的双层事务、
重复连接生命周期和多数据库同步写存在明确优化空间。应先减少每次 Add 的持久化边界和写
放大，再决定是否需要更换存储引擎。
