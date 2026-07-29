"""Regression checks for search- and AI-readable documentation artifacts."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_pages_workflow_publishes_ai_readable_entry_points() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "scripts/build_bilingual_docs.py" in workflow
    assert "cp llms.txt site/llms.txt" in workflow
    assert "cp llms-full.txt site/llms-full.txt" in workflow
    assert "scripts/update_sitemap_lastmod.py" in workflow
    assert "scripts/check_docs_discovery.py" in workflow
    assert "git diff --exit-code -- llms-full.txt" in workflow


def test_pages_workflow_notifies_indexnow_after_deployment() -> None:
    workflow = _read(".github/workflows/docs.yml")

    assert "Verify deployed discovery endpoints" in workflow
    assert "https://api.indexnow.org/indexnow" in workflow
    assert "guides/agent-stock-backtesting/" in workflow
    assert "zh/guides/agent-stock-backtesting/" in workflow


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
    assert 'hreflang="x-default"' in override


def test_material_site_has_matching_english_and_chinese_projects() -> None:
    english = _read("mkdocs.yml")
    chinese = _read("mkdocs.zh.yml")

    assert "docs_dir: docs/en" in english
    assert "language: en" in english
    assert "site_url: https://hephaestlab.github.io/TraderHarness/" in english
    assert "link: /TraderHarness/zh/" in english
    assert "docs_dir: docs" in chinese
    assert "language: zh" in chinese
    assert "site_url: https://hephaestlab.github.io/TraderHarness/zh/" in chinese
    assert "link: /TraderHarness/" in chinese


def test_every_public_page_has_a_matching_english_source() -> None:
    chinese_pages = re.findall(
        r"^\s+- [^:]+: (.+\.md)$", _read("mkdocs.zh.yml"), flags=re.MULTILINE
    )
    english_pages = re.findall(
        r"^\s+- [^:]+: (.+\.md)$", _read("mkdocs.yml"), flags=re.MULTILINE
    )

    assert chinese_pages == english_pages
    for page in english_pages:
        content = _read(f"docs/en/{page}")
        assert "lang: en" in content
        assert "description:" in content


def test_english_evergreen_guide_is_in_ai_documentation_bundle() -> None:
    builder = _read("scripts/build_llms_full.py")
    index = _read("llms.txt")

    assert '"en" / "guides" / "agent-stock-backtesting.md"' in builder
    assert "/guides/agent-stock-backtesting/" in index


def test_chinese_search_intent_guide_is_discoverable() -> None:
    builder = _read("scripts/build_llms_full.py")
    index = _read("llms.txt")
    guide = _read("docs/guides/agent-stock-backtesting.md")
    mkdocs = _read("mkdocs.zh.yml")

    assert '"guides" / "agent-stock-backtesting.md"' in builder
    assert "/zh/guides/agent-stock-backtesting/" in index
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
    pages = re.findall(
        r"^\s+- [^:]+: (.+\.md)$", _read("mkdocs.zh.yml"), flags=re.MULTILINE
    )
    descriptions: set[str] = set()
    for page in pages:
        content = _read(f"docs/{page}")
        assert "description:" in content, f"{page} needs a meta description"
        description = next(line for line in content.splitlines() if line.startswith("description:"))
        assert description not in descriptions, f"{page} reuses a meta description"
        descriptions.add(description)


def test_masking_experiment_localizes_dynamic_interface_copy() -> None:
    script = _read("docs/javascripts/masking-ab-showcase.js")

    assert 'startsWith("zh")' in script
    assert 'dateMasking: "Date masking"' in script
    assert 'dateMasking: "日期掩码"' in script
    assert 'unmasked: "未掩码对照组"' in script
    assert 'boundary: "解读边界"' in script
