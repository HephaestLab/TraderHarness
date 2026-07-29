---
seo_title: TraderHarness China A-share Dataset — Daily, 5-minute, and Point-in-time Data
description: Five years of full-market A-share daily and 5-minute bars, announcements, policy news, fundamentals, valuation, dividends, CSI 300, integrity checks, and licensing boundaries.
lang: en
---

# Data and licensing

The canonical A-share release contains five years of full-market daily and 5-minute bars plus announcements, policy news, fundamentals, valuation, dividends, and a CSI 300 benchmark.

## Integrity

`traderharness data download --full` verifies every object against the release manifest before atomically replacing the local dataset. `traderharness data update` uses watermarks, deterministic deduplication, and atomic writes.

The data doctor checks required schemas and date ranges, natural-key duplicates, annual intraday coverage, stale symbols, non-A-share announcement codes, and metadata consistency.

The v1.0 canonical build contains 284,219,844 deduplicated 5-minute records. Release audits reported complete annual symbol coverage for the active daily universe, no stale symbol at the final 5-minute watermark, and zero natural-key duplicates in the verification sample.

## Public release policy

Public news tables retain templated titles and omit licensed full text. Company templates resolve to neutral identities only at runtime. This preserves a usable point-in-time dataset without redistributing restricted content.

## Storage layout

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

Market-data licensing varies by provider and jurisdiction. Review upstream terms before redistribution or commercial deployment.
