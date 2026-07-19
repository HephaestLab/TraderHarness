# Frequently asked questions

## Why evaluate a new LLM on history it may have seen?

A knowledge cutoff is not an information barrier. TraderHarness removes the absolute date and company identity at
every agent-facing boundary, reveals intraday bars progressively, and audits serialized artifacts for lexical
leakage. Famous events can still be inferred semantically, so rigorous work should report mask settings and include a
blinded/unblinded comparison where appropriate.

## Does entity masking change trading rules?

No. Real codes are shuffled within compatible A-share board groups. A ChiNext or STAR Market pseudo-code retains the
historical board's price-limit behavior. Matching always uses the internally resolved real instrument.

## Is the full dataset synthetic?

No. Acceptance tests and published runs use historical full-market data. The no-key demo is a deterministic replay of
a real masked run; it does not substitute generated prices.

## Is `compare` a shared multi-agent portfolio?

No. `compare` gives each agent an isolated portfolio. For a TradingAgents-style setup, use a committee: advisors are
read-only and one Trader controls one portfolio.

## Can replay silently call the model provider?

No. Requests are fingerprinted. A mismatch or exhausted cassette fails closed.

## Can the UI be exposed as a hosted service?

Not safely in its current form. Agent-authored Python is executable behind the local HTTP server. The sandbox guard
protects backtest data boundaries, not a hostile multi-tenant deployment. Keep the server on localhost.

## Does a profitable backtest imply a deployable strategy?

No. TraderHarness does not model market impact and historical performance does not guarantee future returns. It is
research infrastructure, not investment advice or a broker.

## Which agents and model does the README showcase use?

The four-agent showcase compares the bundled `trend-breakout`, `quality-compounder`, `event-hawk`, and
`quant-researcher` cards over 2024-03-04 to 2024-03-29 with entity masking enabled, using `deepseek-v4-pro` in
thinking mode as the executor. Performance figures are published only after that exact run completes and passes
`traderharness audit`; the README does not publish estimated or placeholder numbers as if they were real.

## Is `traderharness demo` the same as paper trading?

No. `demo` replays a single recorded, masked historical day with no network calls. Paper trading — a forward
simulated mode against a streaming feed — does not exist yet; see [Roadmap](roadmap.md).
