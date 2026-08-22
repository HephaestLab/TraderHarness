---
seo_title: TraderHarness A 股回测数据集：日线、5 分钟线与时点数据
description: TraderHarness 五年全市场 A 股数据说明，覆盖日线、5 分钟线、公告、政策新闻、基本面、估值、分红、沪深 300、完整性校验与许可边界。
lang: zh-CN
---

# 数据与许可

规范 A 股发布版包含五年全市场日线与 5 分钟线，以及公告、政策新闻、基本面、估值、分红和沪深 300 基准。

## 完整性

`traderharness data download --full` 会按发布清单逐项校验后才原子替换本地数据集；`traderharness data update` 使用水位线、确定性去重与原子写入。

增量更新按依赖拓扑执行：日线先合并，随后才根据新区间的正成交量日线发现分钟股票池。基本面和分红也参与增量更新；`business_segments.parquet` 仍是发布快照，因为当前免费源没有稳定、结构化且许可清晰的主营构成增量接口。

```bash
traderharness data status
traderharness data update --end 2026-08-21
traderharness data doctor --start 2026-03-01 --end 2026-08-21
```

回测启动前会执行同一覆盖门禁。日线、沪深 300 或已安装的 5 分钟数据只要没有覆盖目标交易日，运行就会直接失败，不再以空行情继续生成结果。

### 免费源的请求预算

所有 HTTP 提供方共用线程安全的请求门：固定请求预算、`Retry-After`、指数退避、429 统计和 403 熔断。失败进度写入 `.pipeline/latest.json`；东方财富分钟数据按股票持久缓存，恢复时只请求未完成股票。默认预算可向下调整：

| 环境变量 | 默认预算 | 用途 |
|---|---:|---|
| `TRADERHARNESS_EASTMONEY_RPS` | 2.5 请求/秒 | 5 分钟和模拟盘关注池 1 分钟 |
| `TRADERHARNESS_BAOSTOCK_RPS` | 4 请求/秒 | 日线、估值、基本面、分红、基准 |
| `TRADERHARNESS_CNINFO_RPS` | 1 请求/秒 | 公告 |
| `TRADERHARNESS_CLS_RPS` | 1.4 请求/秒 | 新闻 |

这些预算保证 TraderHarness 自己不会超过配置速率；第三方仍可能因共享出口、隐性配额或规则变化返回限流。遇到 429 会服从上游等待时间，遇到 403 会停止继续施压并保留断点，而不是切换 IP 绕过限制。

模拟盘的 1 分钟数据使用最近五日分时接口，只查询持仓、自选股和当次候选的小集合；市场宽度仍使用低频全市场快照。因此请求量随 Agent 关注集合增长，而不是随全市场约五千只股票每分钟增长。

仓库自带的数据医生（data doctor）检查：

- 必需 schema 与日期范围
- 自然键重复
- 5 分钟线年度覆盖率
- 过期标的与数据集对齐
- 非 A 股公告代码非法值
- 元数据一致性

v1.0 规范构建包含 284,219,844 条去重后的 5 分钟记录。发布审计中，活跃日线股票池的年度标的覆盖率达到 100%，最终 5 分钟水位线处无滞后标的，验证样本中自然键零重复。

## 公开发布策略

公开新闻表只保留模板化标题，移除有授权限制的正文。公司模板只在运行时解析为中性身份。这在保护评测完整性的同时，让源数据集依然可用于时点过滤。

## 存储结构

```text
~/.traderharness/dataset/
├── daily.parquet
├── 5min_clean/
├── announcements.parquet
├── news_cls.parquet
├── fundamentals.parquet
├── valuation.parquet
├── dividends.parquet
├── index_300.parquet
└── metadata.json
```

行情数据许可因供应商与司法辖区而异。再分发或商用部署前请核实上游条款。
