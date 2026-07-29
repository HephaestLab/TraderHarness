"""Build the English root site and the matching Simplified Chinese subsite."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DOCS = ROOT / "docs"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"
HTML_LANGUAGE_PATTERN = re.compile(
    r"(<html\b[^>]*\blang=)(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)


def _build(config: str, destination: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            config,
            "--site-dir",
            str(destination),
        ],
        cwd=ROOT,
        check=True,
    )


def _copy_shared_assets() -> None:
    for directory in ("assets", "javascripts", "stylesheets"):
        shutil.copytree(DOCS / directory, SITE / directory, dirs_exist_ok=True)
    for filename in ("robots.txt", "bc1dff31c472cb4a322c024d3b0562d6.txt"):
        shutil.copy2(DOCS / filename, SITE / filename)
    for filename in ("llms.txt", "llms-full.txt"):
        shutil.copy2(ROOT / filename, SITE / filename)


def _set_html_language(directory: Path, language: str) -> None:
    pages = list(directory.rglob("index.html"))
    not_found = directory / "404.html"
    if not_found.is_file():
        pages.append(not_found)
    for page in pages:
        html = page.read_text(encoding="utf-8")
        replaced, count = HTML_LANGUAGE_PATTERN.subn(rf'\g<1>"{language}"', html, count=1)
        if count != 1:
            raise RuntimeError(f"Could not set HTML language for {page}")
        page.write_text(replaced, encoding="utf-8")


def _merge_sitemaps() -> None:
    ElementTree.register_namespace("", SITEMAP_NAMESPACE)
    root_sitemap = SITE / "sitemap.xml"
    chinese_sitemap = SITE / "zh" / "sitemap.xml"
    tree = ElementTree.parse(root_sitemap)
    root = tree.getroot()
    known = {
        location.text
        for location in root.findall(f"{{{SITEMAP_NAMESPACE}}}url/{{{SITEMAP_NAMESPACE}}}loc")
    }
    chinese_root = ElementTree.parse(chinese_sitemap).getroot()
    for entry in chinese_root.findall(f"{{{SITEMAP_NAMESPACE}}}url"):
        location = entry.find(f"{{{SITEMAP_NAMESPACE}}}loc")
        if location is not None and location.text not in known:
            root.append(deepcopy(entry))
            known.add(location.text)
    tree.write(root_sitemap, encoding="utf-8", xml_declaration=True)


def _write_legacy_redirect() -> None:
    destination = SITE / "guides" / "llm-trading-agent-backtesting" / "index.html"
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = "https://hephaestlab.github.io/TraderHarness/guides/agent-stock-backtesting/"
    destination.write_text(
        "<!doctype html><html lang=\"en\"><head>"
        f"<meta charset=\"utf-8\"><link rel=\"canonical\" href=\"{target}\">"
        "<meta name=\"description\" content=\"The TraderHarness LLM trading-agent "
        "backtesting guide has moved to its canonical bilingual URL.\">"
        f"<meta http-equiv=\"refresh\" content=\"0; url={target}\">"
        "<meta name=\"robots\" content=\"noindex,follow\">"
        "<title>Moved | TraderHarness</title></head><body>"
        f"<p>This guide moved to <a href=\"{target}\">{target}</a>.</p>"
        "</body></html>",
        encoding="utf-8",
    )


def main() -> None:
    if SITE.exists():
        shutil.rmtree(SITE)
    _build("mkdocs.yml", SITE)
    _build("mkdocs.zh.yml", SITE / "zh")
    _set_html_language(SITE / "zh", "zh-CN")
    _copy_shared_assets()
    _merge_sitemaps()
    _write_legacy_redirect()
    print("Built bilingual documentation: English / and Simplified Chinese /zh/")


if __name__ == "__main__":
    main()
