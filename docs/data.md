# 数据与许可

规范 A 股发布版包含五年全市场日线与 5 分钟线，以及公告、政策新闻、基本面、估值、分红和沪深 300 基准。

## 完整性

`traderharness data download --full` 会按发布清单逐项校验后才原子替换本地数据集；`traderharness data update` 使用水位线、确定性去重与原子写入。

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
