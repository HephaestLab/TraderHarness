# Security policy

## Supported versions

Security fixes are applied to the latest released version.

## Reporting

Do not open a public issue for credential exposure, sandbox escape, path-guard bypass, future-data leakage, entity/date deanonymization, or a way to bypass `TradingBus.place_order()`.

Use GitHub's private security advisory flow for `HephaestLab/TraderHarness`. Include a minimal reproduction, affected version, impact, and any known mitigation. Please do not include live API keys or licensed market data.

## Scope

High-priority reports include:

- reading the canonical dataset from the execution sandbox
- accessing current-day or future information through any agent-facing outlet
- recovering real entities when entity masking is enabled
- arbitrary filesystem or command access outside the sandbox workspace
- changing portfolio state without the validated order path
- replay silently calling a network provider

TraderHarness is not a broker, wallet, or live order-routing service. Vulnerabilities in upstream market-data services should be reported to their maintainers.
