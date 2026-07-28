"""Regression checks for search- and AI-readable documentation artifacts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pages_workflow_publishes_ai_readable_entry_points() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "cp llms.txt site/llms.txt" in workflow
    assert "cp llms-full.txt site/llms-full.txt" in workflow


def test_pages_workflow_notifies_indexnow_after_deployment() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "Verify deployed discovery endpoints" in workflow
    assert "https://api.indexnow.org/indexnow" in workflow
    assert "guides/llm-trading-agent-backtesting/" in workflow


def test_robots_file_allows_crawling_and_advertises_sitemap() -> None:
    robots = _read("docs/robots.txt")

    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert "Sitemap: https://hephaestlab.github.io/TraderHarness/sitemap.xml" in robots


def test_site_head_advertises_ai_readable_entry_points() -> None:
    override = _read("docs/overrides/main.html")

    assert 'href="https://hephaestlab.github.io/TraderHarness/llms.txt"' in override
    assert 'href="https://hephaestlab.github.io/TraderHarness/llms-full.txt"' in override


def test_english_evergreen_guide_is_in_ai_documentation_bundle() -> None:
    builder = _read("scripts/build_llms_full.py")
    index = _read("llms.txt")

    assert '"guides" / "llm-trading-agent-backtesting.md"' in builder
    assert "/guides/llm-trading-agent-backtesting/" in index
