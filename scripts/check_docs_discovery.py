"""Fail CI when the built documentation loses critical SEO/GEO contracts."""

from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
BASE_URL = "https://hephaestlab.github.io/TraderHarness/"


class DiscoveryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.description = ""
        self.canonical: list[str] = []
        self.alternates: dict[str, str] = {}
        self.json_ld: list[str] = []
        self.html_language = ""
        self._in_json_ld = False
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        if tag == "html":
            self.html_language = attributes.get("lang", "")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta" and attributes.get("name", "").lower() == "description":
            self.description = attributes.get("content", "").strip()
        elif tag == "link" and attributes.get("rel", "").lower() == "canonical":
            self.canonical.append(attributes.get("href", ""))
        elif tag == "link" and attributes.get("rel", "").lower() == "alternate":
            language = attributes.get("hreflang", "")
            if language:
                self.alternates[language] = attributes.get("href", "")
        elif tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._script_parts).strip())
            self._in_json_ld = False
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._in_json_ld:
            self._script_parts.append(data)


def _parse_page(path: Path) -> tuple[DiscoveryParser, list[object]]:
    parser = DiscoveryParser()
    parser.feed(path.read_text(encoding="utf-8"))
    schemas = []
    for payload in parser.json_ld:
        schemas.append(json.loads(payload))
    return parser, schemas


def _schema_types(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        kind = value.get("@type")
        if isinstance(kind, str):
            found.add(kind)
        elif isinstance(kind, list):
            found.update(item for item in kind if isinstance(item, str))
        for item in value.values():
            found.update(_schema_types(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_schema_types(item))
    return found


def _check_all_pages() -> None:
    titles: dict[str, Path] = {}
    descriptions: dict[str, Path] = {}
    for path in sorted(SITE.rglob("index.html")):
        parser, _ = _parse_page(path)
        if not parser.title.strip():
            raise AssertionError(f"Missing title: {path}")
        if not parser.description:
            raise AssertionError(f"Missing meta description: {path}")
        if len(parser.canonical) != 1 or not parser.canonical[0].startswith(BASE_URL):
            raise AssertionError(f"Invalid canonical URL: {path}: {parser.canonical}")
        if parser.title in titles:
            raise AssertionError(f"Duplicate title: {path} and {titles[parser.title]}")
        if parser.description in descriptions:
            raise AssertionError(
                f"Duplicate description: {path} and {descriptions[parser.description]}"
            )
        titles[parser.title] = path
        descriptions[parser.description] = path


def _check_primary_guides() -> None:
    chinese_path = SITE / "zh" / "guides" / "agent-stock-backtesting" / "index.html"
    english_path = SITE / "guides" / "agent-stock-backtesting" / "index.html"
    chinese, chinese_schemas = _parse_page(chinese_path)
    english, english_schemas = _parse_page(english_path)

    if "Agent 炒股如何回测" not in chinese.title:
        raise AssertionError(f"Primary Chinese intent is missing from title: {chinese.title}")
    if chinese.html_language != "zh-CN" or english.html_language != "en":
        raise AssertionError(
            f"Guide language mismatch: zh={chinese.html_language!r}, en={english.html_language!r}"
        )
    expected_alternates = {
        "zh-CN": urljoin(BASE_URL, "zh/guides/agent-stock-backtesting/"),
        "en": urljoin(BASE_URL, "guides/agent-stock-backtesting/"),
        "x-default": urljoin(BASE_URL, "guides/agent-stock-backtesting/"),
    }
    if chinese.alternates != expected_alternates:
        raise AssertionError(f"Chinese hreflang mismatch: {chinese.alternates}")
    if english.alternates != expected_alternates:
        raise AssertionError(f"English hreflang mismatch: {english.alternates}")

    for label, schemas in (("Chinese", chinese_schemas), ("English", english_schemas)):
        types = _schema_types(schemas)
        required = {"WebSite", "SoftwareSourceCode", "TechArticle", "BreadcrumbList", "FAQPage"}
        missing = required - types
        if missing:
            raise AssertionError(f"{label} guide is missing schema types: {sorted(missing)}")


def _check_discovery_files() -> None:
    sitemap = SITE / "sitemap.xml"
    root = ElementTree.parse(sitemap).getroot()
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = {item.text for item in root.findall("sm:url/sm:loc", namespace) if item.text}
    required = {
        urljoin(BASE_URL, "guides/agent-stock-backtesting/"),
        urljoin(BASE_URL, "zh/guides/agent-stock-backtesting/"),
    }
    if not required.issubset(urls):
        raise AssertionError(f"Sitemap is missing priority URLs: {sorted(required - urls)}")
    forbidden = ("/plans/", "/v0.1.0-plan/", "/design/pixel-trader-scene/")
    leaked = sorted(url for url in urls if any(part in url for part in forbidden))
    if leaked:
        raise AssertionError(f"Internal planning pages leaked into sitemap: {leaked}")

    robots = (SITE / "robots.txt").read_text(encoding="utf-8")
    if "Allow: /" not in robots or f"Sitemap: {BASE_URL}sitemap.xml" not in robots:
        raise AssertionError("robots.txt does not expose the public sitemap")
    for name in ("llms.txt", "llms-full.txt"):
        if not (SITE / name).is_file():
            raise AssertionError(f"Missing AI-readable discovery file: {name}")


def _check_bilingual_page_map() -> None:
    english_pages = {
        path.relative_to(SITE).as_posix()
        for path in SITE.rglob("index.html")
        if "zh" not in path.relative_to(SITE).parts
        and "llm-trading-agent-backtesting" not in path.parts
    }
    chinese_pages = {
        path.relative_to(SITE / "zh").as_posix()
        for path in (SITE / "zh").rglob("index.html")
    }
    if english_pages != chinese_pages:
        raise AssertionError(
            "English/Chinese page maps differ: "
            f"English only={sorted(english_pages - chinese_pages)}, "
            f"Chinese only={sorted(chinese_pages - english_pages)}"
        )
    for relative in sorted(english_pages):
        english, _ = _parse_page(SITE / relative)
        chinese, _ = _parse_page(SITE / "zh" / relative)
        page_path = relative.removesuffix("index.html")
        english_url = urljoin(BASE_URL, page_path)
        chinese_url = urljoin(BASE_URL, f"zh/{page_path}")
        expected = {
            "en": english_url,
            "zh-CN": chinese_url,
            "x-default": english_url,
        }
        if english.html_language != "en" or chinese.html_language != "zh-CN":
            raise AssertionError(
                f"Language mismatch for {relative}: "
                f"English={english.html_language!r}, Chinese={chinese.html_language!r}"
            )
        if english.alternates != expected or chinese.alternates != expected:
            raise AssertionError(
                f"Reciprocal hreflang mismatch for {relative}: "
                f"English={english.alternates}, Chinese={chinese.alternates}"
            )
    if not (SITE / "search" / "search_index.json").is_file():
        raise AssertionError("Missing English search index")
    if not (SITE / "zh" / "search" / "search_index.json").is_file():
        raise AssertionError("Missing Chinese search index")


def main() -> None:
    _check_all_pages()
    _check_primary_guides()
    _check_bilingual_page_map()
    _check_discovery_files()
    print("Documentation discovery checks passed")


if __name__ == "__main__":
    main()
