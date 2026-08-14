"""Render README.md to a self-contained HTML preview with all local images
inlined as base64 data URIs, so it displays exactly as GitHub would render it
(no repo-relative path resolution needed)."""

import base64
import mimetypes
import re
from pathlib import Path

from markdown_it import MarkdownIt

import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "README.md")
OUT = ROOT / (SRC.stem + "_preview.html")


def inline_local_images(html: str) -> str:
    def repl(match: re.Match) -> str:
        prefix, src, suffix = match.group(1), match.group(2), match.group(3)
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        path = ROOT / src
        if not path.is_file():
            print(f"MISSING: {src}")
            return match.group(0)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".svg":
            mime = "image/svg+xml"
        b64 = base64.b64encode(path.read_bytes()).decode()
        print(f"inlined: {src} ({path.stat().st_size // 1024} KB)")
        return f"{prefix}data:{mime};base64,{b64}{suffix}"

    return re.sub(r'(src=")([^"]+)(")', repl, html)


def main() -> None:
    md = MarkdownIt("commonmark", {"html": True, "linkify": True})
    html = md.render(SRC.read_text(encoding="utf-8"))
    html = inline_local_images(html)
    OUT.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>README preview</title>"
        "<style>body{max-width:900px;margin:2rem auto;padding:0 1rem;"
        "font-family:-apple-system,'Segoe UI',sans-serif;line-height:1.6}"
        "img{max-width:100%}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:4px 8px}"
        "code{background:#f0f0f0;padding:1px 4px}</style>"
        "</head><body>" + html + "</body></html>",
        encoding="utf-8",
    )
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
