"""Build per-platform publish bodies from article-main.md."""
import re
from pathlib import Path

SRC = Path("promo/domestic/article-main.md")
OUT = Path("promo/domestic/final")
OUT.mkdir(parents=True, exist_ok=True)

text = SRC.read_text(encoding="utf-8")
# Strip the meta header (up to the first horizontal rule) and the trailing zhihu note
body = text.split("\n---\n", 1)[1]
body = body.split("### 知乎专属")[0].rstrip() + "\n"

IMG_BASE = "https://hephaestlab.github.io/TraderHarness/assets"
body = body.replace("[图1：控制台 demo GIF]",
                    f"![TraderHarness 控制台演示]({IMG_BASE}/traderharness-demo.gif)")
body = body.replace("[图2：结果工作台——净值曲线、回撤、逐笔复盘]",
                    f"![回测结果研究工作台]({IMG_BASE}/results-workbench.png)")
body = body.replace("[图3：像素办公室]",
                    f"![像素风办公室：Agent 上班直播]({IMG_BASE}/office-live.png)")

titles = {
    "juejin": "LLM 炒股 Agent 遍地，却连一个不作弊的考场都没有",
    "csdn": "给 Trading Agent 做回测，最大的坑是模型“背过答案”",
    "zhihu": "为什么说现在大多数 AI 炒股回测，是在自欺欺人？",
}

for platform, title in titles.items():
    (OUT / f"{platform}-title.txt").write_text(title, encoding="utf-8")
    (OUT / f"{platform}-body.md").write_text(body, encoding="utf-8")

# Zhihu needs HTML, not raw markdown
from markdown_it import MarkdownIt

html = MarkdownIt("commonmark", {"html": True}).enable("table").render(body)
(OUT / "zhihu-body.html").write_text(html, encoding="utf-8")
print("built:", [p.name for p in sorted(OUT.iterdir())])
