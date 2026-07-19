# LLM trading backtests without data leakage

TraderHarness treats historical contamination as an environment boundary, not a prompt convention.

## Definitions

**Point-in-time masking** means every value exposed to an agent is filtered by the simulated clock before it leaves
the environment. Daily bars are strictly earlier than the current trading date, 5-minute bars stop at the active
sub-window, and fundamental records cannot have a future publication date.

**Date anonymization** replaces an absolute agent-facing calendar date with a calendar-day offset from the simulated
present. The current date is `D+0`; the previous calendar day is `D-1`. Wall-clock times remain visible.

**Entity masking** is a deterministic run-wide bijection from real A-share codes and known company aliases to neutral
pseudo-identities. Codes are shuffled within compatible board groups so price-limit rules survive anonymization.

**The three-phase trading loop** is a bounded market day consisting of pre-market research with orders disabled, a
progressively revealed 09:30–10:00 open window, and a progressively revealed 14:30–15:00 close window.

## Egress coverage

The masks apply to:

- daily and intraday K-lines;
- market screens, fundamentals, valuation, announcements, and policy news;
- portfolio and watchlist views;
- Python sandbox DataFrames returned by `traderharness_api`;
- model responses, reasoning fields, tool arguments, and committee memos;
- cross-day memory, persisted trajectories, replay cassettes, comparisons, and SFT exports.

Pseudo-codes sent back through tools are resolved internally before matching. The resulting portfolio is rendered
through the same forward map, so the agent never needs a real code.

![Date and entity mask transformation](assets/dual-mask.svg)

## Artifact audit

```bash
traderharness audit result.json replay.jsonl export.parquet
```

The auditor checks known real entity aliases, six-digit A-share code leakage, absolute ISO/Chinese dates, and
month-day forms. The v1.0 release acceptance run audited a serialized one-month DeepSeek trajectory and detected zero
real entity aliases or absolute dates after the final egress fixes.

That result has a narrow meaning: it verifies the known lexical and calendar egress contract. It does not prove that
a model cannot infer a famous company from a unique financial pattern, product, executive, or event. For publishable
evaluations, report the mask configuration and seed, retain the audit output, and compare blinded with unblinded runs
when semantic re-identification is material.

## Execution leakage

Information masking is insufficient if the matching engine lets the model inspect a full intraday window and then
select an earlier favorable price. TraderHarness reveals each open/close sub-window before its eligible fill and
routes every order through `TradingBus.place_order()`. The action sequence therefore cannot choose prices that were
not visible at decision time.
