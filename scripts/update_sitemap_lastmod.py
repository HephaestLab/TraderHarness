"""Replace build-time sitemap dates with each source page's real Git revision time."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITEMAP = ROOT / "site" / "sitemap.xml"
SITE_PREFIX = "/TraderHarness/"
SITEMAP_NAMESPACE = "http://www.sitemaps.org/schemas/sitemap/0.9"


def _source_for_url(url: str) -> Path | None:
    path = urlparse(url).path
    if not path.startswith(SITE_PREFIX):
        return None
    relative = path[len(SITE_PREFIX) :].strip("/")
    if relative == "zh" or relative.startswith("zh/"):
        localized = relative.removeprefix("zh").strip("/")
        source = DOCS / ("index.md" if not localized else f"{localized}.md")
    else:
        source = DOCS / "en" / ("index.md" if not relative else f"{relative}.md")
    return source if source.is_file() else None


def _revision_time(source: Path) -> str:
    relative = source.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cI", "--", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    value = result.stdout.strip()
    if value:
        return value
    modified = datetime.fromtimestamp(source.stat().st_mtime, tz=UTC)
    return modified.isoformat(timespec="seconds")


def main() -> None:
    if not SITEMAP.is_file():
        raise SystemExit(f"Missing generated sitemap: {SITEMAP}")

    ElementTree.register_namespace("", SITEMAP_NAMESPACE)
    tree = ElementTree.parse(SITEMAP)
    root = tree.getroot()
    updated = 0
    for entry in root.findall(f"{{{SITEMAP_NAMESPACE}}}url"):
        location = entry.find(f"{{{SITEMAP_NAMESPACE}}}loc")
        last_modified = entry.find(f"{{{SITEMAP_NAMESPACE}}}lastmod")
        if location is None or location.text is None or last_modified is None:
            continue
        source = _source_for_url(location.text)
        if source is None:
            continue
        last_modified.text = _revision_time(source)
        updated += 1

    tree.write(SITEMAP, encoding="utf-8", xml_declaration=True)
    print(f"Updated {updated} sitemap lastmod values from source revisions")


if __name__ == "__main__":
    main()
