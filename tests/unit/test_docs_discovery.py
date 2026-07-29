"""Regression checks for search- and AI-readable documentation artifacts."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pages_workflow_publishes_ai_readable_entry_points() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "cp llms.txt site/llms.txt" in workflow
    assert "cp llms-full.txt site/llms-full.txt" in workflow
    assert "scripts/update_page_languages.py" in workflow
    assert "scripts/update_sitemap_lastmod.py" in workflow
    assert "scripts/check_docs_discovery.py" in workflow
    assert "git diff --exit-code -- llms-full.txt" in workflow


def test_pages_workflow_notifies_indexnow_after_deployment() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "Verify deployed discovery endpoints" in workflow
    assert "https://api.indexnow.org/indexnow" in workflow
    assert "guides/agent-stock-backtesting/" in workflow
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
    assert '"@type": "WebSite"' in override
    assert '"@type": "TechArticle"' in override
    assert '"@type": "FAQPage"' in override
    assert 'hreflang="zh-CN"' in override
    assert 'hreflang="en"' in override


def test_english_evergreen_guide_is_in_ai_documentation_bundle() -> None:
    builder = _read("scripts/build_llms_full.py")
    index = _read("llms.txt")

    assert '"guides" / "llm-trading-agent-backtesting.md"' in builder
    assert "/guides/llm-trading-agent-backtesting/" in index


def test_chinese_search_intent_guide_is_discoverable() -> None:
    builder = _read("scripts/build_llms_full.py")
    index = _read("llms.txt")
    guide = _read("docs/guides/agent-stock-backtesting.md")
    mkdocs = _read("mkdocs.yml")

    assert '"guides" / "agent-stock-backtesting.md"' in builder
    assert "/guides/agent-stock-backtesting/" in index
    assert "Agent 炒股如何回测" in guide
    assert "AI 炒股回测指南" in mkdocs
    assert "datePublished:" in guide
    assert "dateModified:" in guide
    assert "faq:" in guide


def test_homepage_targets_the_primary_chinese_search_intent() -> None:
    homepage = _read("docs/index.md")

    assert "seo_title:" in homepage
    assert "Agent 炒股如何回测" in homepage
    assert "guides/agent-stock-backtesting.md" in homepage


def test_every_navigation_page_has_unique_search_metadata() -> None:
    pages = re.findall(r"^\s+- [^:]+: (.+\.md)$", _read("mkdocs.yml"), flags=re.MULTILINE)
    descriptions: set[str] = set()
    for page in pages:
        content = _read(f"docs/{page}")
        assert "description:" in content, f"{page} needs a meta description"
        description = next(line for line in content.splitlines() if line.startswith("description:"))
        assert description not in descriptions, f"{page} reuses a meta description"
        descriptions.add(description)
