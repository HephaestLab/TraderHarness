# Changelog

All notable changes to TraderHarness are documented here.

## 1.0.0 — 2026-07-17

First public research beta.

### Environment and data

- Added a five-year full-market A-share dataset pipeline for daily and 5-minute bars, announcements, policy news,
  fundamentals, valuation, dividends, and CSI 300.
- Added canonical loaders, atomic incremental updates, release manifests, SHA-256 verification, and `data doctor`
  integrity checks.
- Enforced zero market-data I/O after backtest preload.

### Evaluation integrity

- Added strict point-in-time masking across daily, intraday, news, announcement, fundamental, and sandbox egress.
- Added deterministic calendar and company-entity anonymization with board-semantics preservation.
- Added serialized-artifact leakage auditing and real-name/date sanitation for model-generated text.
- Consolidated matching through `TradingBus.place_order()`.

### Agents and trajectories

- Added the three-phase pre-market, open-window, and close-window agent loop.
- Added independent multi-agent comparison and a single-executor, multi-role committee reference implementation.
- Added full-fidelity LLM exchange trajectories, fail-closed fingerprinted replay, and OpenAI-style SFT export.
- Added CSI 300 performance comparison and behavioral evaluation metrics.

### Product and release engineering

- Replaced the Streamlit interface with a local FastAPI and React research console.
- Added a live pixel-art operations floor, reconnectable WebSocket journal, K-line execution review, decision evidence,
  benchmark, drawdown, and transaction research views.
- Added an unprivileged multi-stage Docker image, local-only Compose configuration, PyPI packaging, GHCR release
  workflow, MkDocs site, and Windows/Linux CI.
