# One-click experience and masked/unmasked A/B implementation plan

Status: approved for implementation
Owner: HephaestLab / TraderHarness
Scope: one-click audited showcase and a reproducible masking experiment

## 1. Outcomes

This work ships two connected capabilities:

1. A zero-credential, zero-dataset browser experience that lets a visitor inspect a real,
   pre-recorded and audited TraderHarness experiment immediately.
2. A reproducible A/B harness that runs the same trading agent with date and entity masking
   enabled or disabled, records every LLM interaction, audits the artifacts, and publishes
   machine-readable results with checksums.

The browser experience is a viewer for recorded evidence. It must never imply that the static
page is executing a live backtest. The executable path remains a local/Colab deterministic replay.

## 2. Non-negotiable experiment boundaries

- Market data is loaded by the normal `BacktestEngine`; the experiment may not introduce a data
  shortcut or network access during a backtest.
- Orders continue to go exclusively through `TradingBus.place_order()`.
- Point-in-time filtering, portfolio ownership and execution-price rules remain unchanged.
- The masked condition keeps both date and entity masking enabled. The unmasked condition is an
  explicit research control and is never the default for normal runs.
- Every live run records an LLM replay. Masked replays must pass the leakage audit. An unmasked
  replay is expected to contain calendar/entity identifiers, so its audit findings are retained as
  evidence instead of being misreported as a failure of the experiment runner.
- No API key is stored in source, artifacts, reports, browser assets or Git history.

## 3. Deliverable A: one-click experience

### 3.1 Public entry

Add an English-first `Masked vs Unmasked` showcase to the documentation site and link it from the
README/docs home page. The page loads a small, versioned JSON artifact and provides:

- a clear `Recorded experiment — not a live backtest` label;
- Masked and Unmasked condition tabs;
- aggregate return, benchmark-relative return, drawdown, trade count and token count;
- paired run cards and an equity-curve comparison;
- masking configuration, model ID, market window, commit SHA and data version;
- audit status with a plain-language explanation of the intentionally unmasked control;
- links to the protocol, raw artifacts and deterministic replay command.

The first meaningful content must not depend on an API key or the full local dataset. It should
render within five seconds on a normal connection and remain usable on a narrow mobile viewport.

### 3.2 Local research console entry

Add `/showcase` to the React console and a prominent dashboard action. It reads the same packaged
showcase contract through a read-only API endpoint. This gives installed users a one-click path
without launching a new model run.

### 3.3 Executable follow-up

The showcase links to the existing deterministic replay path. A notebook/Colab launcher may be
added after the pilot artifact is stable; it must download a checksum-pinned real-data demo fixture
and must label that fixture as a demo rather than a production acceptance dataset.

### 3.4 UX acceptance

- No login, API key or dataset is required to inspect the showcase.
- A visitor can identify the hypothesis, conditions and main result in two interactions or fewer.
- Keyboard focus, button semantics, color contrast and reduced-motion behavior are checked.
- Automated Playwright E2E covers loading, condition switching, audit details and narrow viewport.
- Final local acceptance is performed in the in-app browser against the built application, with a
  screenshot and interaction log retained under the experiment artifact directory.

## 4. Deliverable B: masking A/B experiment

### 4.1 Public A/B conditions

| Condition | Date masking | Entity masking | Purpose |
|---|---:|---:|---|
| `masked` | on | on | contamination-resistant evaluation |
| `unmasked` | off | off | explicit research control |

All other inputs are paired: agent card, model, dates, starting cash, tool contract, market data,
execution rules and entity seed. Run order alternates by repetition to reduce provider-time bias.

The publication pilot uses the README acceptance model, `deepseek-v4-pro` in thinking-high mode,
the pre-declared half-month window `2024-03-04` through `2024-03-15`, and three paired repetitions.
A later robustness run can expand to multiple models/windows after this pilot records cost and
variance.

### 4.2 Engineering work

1. Add `--mask-dates/--no-mask-dates` to `run` (and comparison paths where applicable).
2. Propagate `mask_dates` through card and YAML agents, the local server request, `RunConfig`, result
   documents and Replay Bundle manifests.
3. Keep public defaults masked. An unmasked live run prints a research-control warning.
4. Add a `masking-ab` command that creates a self-contained experiment directory.
5. Add an analyzer that computes paired performance and behavior deltas without claiming that
   performance alone proves contamination.

### 4.3 Experiment artifact contract

```text
<output>/
├── protocol.json              # frozen hypothesis and run matrix
├── manifest.json              # versions, model, data fingerprint and run inventory
├── runs/
│   ├── masked-r01-result.json
│   └── unmasked-r01-result.json
├── replays/
│   ├── masked-r01.jsonl
│   └── unmasked-r01.jsonl
├── analysis.json              # aggregates and paired deltas
├── audit.json                 # policy-aware audit results
├── report.md                  # human-readable result and limitations
└── checksums.sha256           # SHA-256 for every published artifact
```

The manifest records the TraderHarness version, Git commit, Python/platform versions, exact model
ID, endpoint origin without credentials, date window, run order, masking flags, token usage and
dataset metadata/fingerprint.

### 4.4 Metrics

Primary metrics:

- total and benchmark-relative return;
- Sharpe ratio and maximum drawdown;
- trade count, turnover proxy and final value.

Behavior/evidence metrics:

- tool-call count and decision-step count;
- token usage and completion status;
- references to calendar dates or real entities in agent-visible output;
- changes in action, position concentration and timing between paired runs.

Statistics are reported as per-pair deltas plus mean, median and range. With three pilot pairs the
report is descriptive; it must not present a significance claim.

### 4.5 Audit rules

- `masked`: standard leakage audit must pass with zero findings before a run is publishable.
- `unmasked`: standard audit is executed and findings are preserved; calendar/entity findings are
  marked `expected_for_control`. Other integrity failures remain blocking.
- Every result and replay is hashed after all files are finalized.
- The audit report never includes credential values or request headers.

## 5. Test and execution sequence

1. Add failing focused tests for date-mask propagation, manifest compatibility and the showcase API.
2. Implement the smallest changes that satisfy those contracts.
3. Run focused Python and frontend unit tests.
4. Run the bundled masked replay and audit it.
5. Probe the configured OpenAI-compatible endpoint and record only the selected model ID/status.
6. Run one masked/unmasked smoke pair. Stop on any masked audit failure.
7. If the smoke pair is healthy, run the remaining pilot repetitions.
8. Generate aggregate artifacts and the browser showcase JSON.
9. Build the React app and MkDocs site.
10. Run Playwright E2E locally, then repeat the critical journey in the in-app browser.
11. Run the full Python suite, Ruff, frontend tests/build and final artifact audit.

## 6. Completion criteria

Work is complete only when:

- date and entity masking settings are explicit and persisted end to end;
- the same command can reproduce the full experiment matrix;
- all masked artifacts pass leakage audit;
- all output files have verified SHA-256 checksums;
- the public and local one-click experiences load without credentials;
- automated and in-app-browser E2E evidence is retained;
- the report states limitations and does not frame the unmasked control as an investment result or
  model ranking.
