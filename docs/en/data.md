---
seo_title: TraderHarness China A-share Dataset — Daily, 5-minute, and Point-in-time Data
description: Five years of full-market A-share daily and 5-minute bars, announcements, policy news, fundamentals, valuation, dividends, CSI 300, integrity checks, and licensing boundaries.
lang: en
---

# Data and licensing

The canonical A-share release contains five years of full-market daily and 5-minute bars plus announcements, policy news, fundamentals, valuation, dividends, and a CSI 300 benchmark.

## Integrity

`traderharness data download --full` verifies every object against the release manifest before atomically replacing the local dataset. `traderharness data update` uses watermarks, deterministic deduplication, and atomic writes.

Incremental updates follow an explicit dependency graph: daily bars are merged before the active minute universe is discovered. Fundamentals and dividends are incremental as well. `business_segments.parquet` remains a versioned release snapshot because no current free source provides a stable, structured, clearly licensed incremental contract.

```bash
traderharness data status
traderharness data update --end 2026-08-21
traderharness data doctor --start 2026-03-01 --end 2026-08-21
```

The same coverage gate runs before a local backtest. A run fails closed if daily, CSI 300, or an installed 5-minute dataset does not reach the requested exchange session.

### Cooperative request budgets

HTTP providers share thread-safe pacing, `Retry-After` handling, exponential backoff, 429 metrics, and a 403 circuit breaker. Pipeline progress is persisted in `.pipeline/latest.json`; Eastmoney minute downloads checkpoint each symbol and resume only missing work.

| Environment variable | Default | Source |
|---|---:|---|
| `TRADERHARNESS_EASTMONEY_RPS` | 2.5 requests/s | 5-minute and paper watch-universe 1-minute bars |
| `TRADERHARNESS_BAOSTOCK_RPS` | 4 requests/s | daily, valuation, fundamentals, dividends, benchmark |
| `TRADERHARNESS_CNINFO_RPS` | 1 request/s | announcements |
| `TRADERHARNESS_CLS_RPS` | 1.4 requests/s | news |

These budgets guarantee that TraderHarness does not exceed its configured pace. A third party may still throttle a shared IP or change an undocumented quota. TraderHarness obeys 429 cooldowns, stops pressure on 403, and keeps resumable state; it does not rotate IPs to evade an upstream restriction.

Paper trading retrieves recent one-minute trends only for positions, watchlist entries, and the current candidate set. Broad-market state uses lower-frequency snapshots, so request pressure scales with the Agent's attention set rather than the roughly five-thousand-stock universe every minute.

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
