# Data and licensing

The canonical A-share release contains five years of full-market daily and 5-minute bars plus announcements, policy news, fundamentals, valuation, dividends, and the CSI 300 benchmark.

## Integrity

`traderharness data download --full` verifies every file against the release manifest before atomically replacing the local dataset. `traderharness data update` uses watermarks, deterministic deduplication, and atomic writers.

The repository's data doctor checks:

- required schemas and date ranges
- duplicate natural keys
- annual 5-minute coverage
- stale symbols and dataset alignment
- invalid non-A-share announcement codes
- metadata consistency

The v1.0 canonical build contains 284,219,844 deduplicated 5-minute rows. Annual symbol coverage reached 100% for
the active daily universe in the release audit, with zero lagging symbols at the final 5-minute watermark and zero
duplicate natural keys in the verification sample.

## Public release policy

The public news table retains templated headlines and removes licensed full text. Company templates are resolved to neutral identities only at runtime. This protects evaluation integrity while keeping the source dataset useful for point-in-time filtering.

## Storage

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

Market-data licenses vary by provider and jurisdiction. Verify upstream terms before redistribution or commercial deployment.
