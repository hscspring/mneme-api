# mnemekit 0.8.3 Full Search 真实流量验证

日期：2026-10-10  
来源：Agent Memory Leaderboard 文本赛道 Full 评测  
评测任务：`teval_9abcb4ed9849697f`  
核心版本：mnemekit 0.8.3，commit `2101698`  
API 版本：mneme-api 0.1.16，commit `e8b2e90`

## 结论

0.8.3 已在原生产 Store 和原 Full 检查点上投入运行。Store、schema、projection、Top-K、Evidence budget、tokenizer、业务并发和 HTTP 返回格式均未改变；升级前 API 测试 6/6 通过。

首批 14 条 1,112-history 真实 Search：

| 指标 | 0.8.2 稳定窗口 | 0.8.3 首批窗口 |
| --- | ---: | ---: |
| 样本数 | 32 | 14 |
| 最小值 | 70.696 s | 16.552 s |
| 中位数 | 283.940 s | 23.975 s |
| 平均值 | 258.174 s | 25.357 s |
| 最大值 | 453.571 s | 43.052 s |

按非配对线上流量统计，0.8.3 的中位数约快 11.8 倍，均值约快 10.2 倍。14 条结果均保持 1–3 items、50–53 spans、108,903–112,895 response tokens。线上日志未记录 query 正文，因此此窗口不能替代核心方已完成的同 query Evidence 哈希验证。

平台在约五分钟内从 7,357 推进到 7,371，共完成 14 条；Textual 从 5,796 推进到 5,809，Streaming 从 1,561 推进到 1,562。升级前积压时曾超过十分钟才出现一个 HTTP 200，升级后 1112-history 请求持续以约 17–43 秒完成。

## 部署与资源

- 部署时间：2026-10-10 09:09:46 UTC。
- 新 PID：`133432`。
- RAM：约 1.9 GiB。
- Swap：8 GiB。
- Uvicorn worker：1。
- API 业务并发：1。
- 平台 Search 并发上限：16。
- Store schema：3，无迁移。
- 进程首批窗口 VmHWM：约 1,397 MiB。
- 窗口结束 VmRSS：约 1,114 MiB。
- 窗口结束进程 VmSwap：0。
- 公网与内部 `/health`：HTTP 200。

VmHWM 高于核心离线单查询报告的 784 MiB，因为线上进程连续服务多个请求，Python 分配器会保留已申请内存；它不能与离线单查询峰值直接等同。线上未再出现 0.8.2 后期约 1.7 GiB 常驻并持续换页的状态。

## 解释与后续观察

本次数据证明 0.8.3 针对候选构造的优化命中了生产主瓶颈。候选 source 覆盖后停止、在完整对象物化前选择 source peak，以及复用索引与 trace 不变量，在真实 1.57 GiB Store 上带来了数量级吞吐改善。

当前样本可能受热页缓存、query 难度和平台调度影响，因此最终报告仍应在 Search 阶段结束后补充完整分布、HTTP 200 间隔、超时数量和长期 RSS。生产 Full 继续使用相同任务与检查点，不新建 Full，不清空 Store。
