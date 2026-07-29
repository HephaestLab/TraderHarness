"""Apply per-page front-matter languages to generated MkDocs HTML files."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SITE = ROOT / "site"
LANGUAGE_PATTERN = re.compile(r"^lang:\s*([^\s#]+)\s*$", re.MULTILINE)
HTML_LANGUAGE_PATTERN = re.compile(
    r"(<html\b[^>]*\blang=)(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
    re.IGNORECASE,
)


def _output_for_source(source: Path) -> Path:
    relative = source.relative_to(DOCS)
    if relative.as_posix() == "index.md":
        return SITE / "index.html"
    return SITE / relative.with_suffix("") / "index.html"


def main() -> None:
    updated = 0
    for source in DOCS.rglob("*.md"):
        text = source.read_text(encoding="utf-8")
        language = LANGUAGE_PATTERN.search(text)
        if language is None:
            continue
        output = _output_for_source(source)
        if not output.is_file():
            continue
        html = output.read_text(encoding="utf-8")
        replaced, count = HTML_LANGUAGE_PATTERN.subn(
            rf'\1"{language.group(1)}"',
            html,
            count=1,
        )
        if count != 1:
            raise RuntimeError(f"Could not set HTML language for {output}")
        output.write_text(replaced, encoding="utf-8")
        updated += 1
    print(f"Updated HTML lang attributes for {updated} documentation pages")


if __name__ == "__main__":
    main()
