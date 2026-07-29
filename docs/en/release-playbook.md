---
seo_title: TraderHarness Open-source Launch and Distribution Playbook
description: Maintainer checklist and channel-specific launch drafts for GitHub, Show HN, Reddit, Product Hunt, technical articles, and research discovery.
lang: en
---

# Launch and distribution playbook

This maintainer page contains reusable release checks and draft positioning. Publish only after the repository, package, dataset, documentation, and container links are live.

- Repository: <https://github.com/HephaestLab/TraderHarness>
- Documentation: <https://hephaestlab.github.io/TraderHarness/>
- Dataset: <https://huggingface.co/datasets/ANTICH/traderharness-ashare-5y>
- PyPI: <https://pypi.org/project/traderharness/>

## Release gate

```bash
python -m pip index versions traderharness
python -m pip install --no-cache-dir "traderharness[llm,data,ui]"
traderharness --version
curl --fail https://hephaestlab.github.io/TraderHarness/robots.txt
curl --fail https://hephaestlab.github.io/TraderHarness/llms.txt
curl --fail https://hephaestlab.github.io/TraderHarness/llms-full.txt
```

Do not publish “pip install” or “ready to use” copy while any command fails. PyPI Trusted Publishing must match project `traderharness`, owner `HephaestLab`, repository `TraderHarness`, workflow `release.yml`, and environment `pypi`.

## Search and AI discovery

The documentation workflow checks unique titles and descriptions, canonical URLs, reciprocal language alternates, JSON-LD, the combined sitemap, `robots.txt`, and AI-readable files. After deployment it verifies both languages and notifies IndexNow.

Site owners should also verify Google Search Console and Bing Webmaster Tools, submit `https://hephaestlab.github.io/TraderHarness/sitemap.xml`, and monitor branded and non-branded queries for at least six to eight weeks.

## Positioning

**Problem-first hook:**

> Your trading agent may be cheating without knowing it: the model can recognize the date, company, or exact historical price path.

**One-sentence description:**

> TraderHarness is an open-source, contamination-resistant market environment for evaluating LLM trading agents with point-in-time A-share data, progressive execution, deterministic replay, and auditable trajectories.

Lead with the evaluation contract. Trajectories support reinforcement learning, behavior analysis, and evaluation; SFT conversion is optional rather than the primary identity.

## Show HN draft

**Title**

> Show HN: TraderHarness – auditable backtesting for trading agents that may remember history

**Body**

> Historical LLM trading evaluations are easy to leak: a model may recognize the date, company, or a full price path. TraderHarness treats those as environment boundaries. It filters every data outlet by a simulated clock, progressively reveals 5-minute bars, masks dates and companies, routes fills through one order path, and records fingerprint-replayable trajectories. The no-key demo runs locally. I would especially value criticism of the masking threat model and execution contract.

## Reddit angles

For `r/algotrading`, focus on point-in-time data, execution fairness, and reproducibility. Ask for review of matching assumptions rather than votes.

For `r/LocalLLaMA`, focus on complete trajectories for reinforcement learning, behavior analysis, and evaluation. Explain that the environment records full messages, tool schemas, calls, results, and phase metadata, with optional SFT conversion.

Do not mass-post identical copy across communities.

## Product Hunt

**Tagline**

> Contamination-resistant backtesting for LLM trading agents

**Description**

> An open-source A-share environment for evaluating LLM trading agents without silent data leakage: point-in-time masking, entity/date anonymization, progressive 5-minute execution, fingerprinted replay, and auditable trajectories for RL and evaluation.

## External citation strategy

- Publish one original technical article around historical memorization, not a copied README.
- Submit small, scope-matched pull requests to relevant awesome lists.
- Invite adjacent agent-framework maintainers to run a masked/unmasked comparison.
- Publish a technical report and connect its paper, dataset, and code on Hugging Face.
- Optimize for independent reproductions, technical discussion, and citations rather than low-quality backlinks.
