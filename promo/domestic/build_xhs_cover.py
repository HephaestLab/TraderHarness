r"""Build the 3:4 Xiaohongshu cover card (1080x1440).

Usage: .venv\Scripts\python.exe promo\domestic\build_xhs_cover.py
Output: promo/domestic/final/xhs-cover.png
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "promo" / "domestic" / "final" / "xhs-cover.png"
OFFICE = ROOT / "docs" / "assets" / "office-live.png"

W, H = 1080, 1440
BG = (14, 17, 22)
GREEN = (43, 217, 124)
WHITE = (240, 243, 246)
GRAY = (155, 163, 175)

FONT_DIR = Path(r"C:\Windows\Fonts")
BOLD = str(FONT_DIR / "msyhbd.ttc")
REG = str(FONT_DIR / "msyh.ttc")

# Text kept as escapes so the source file stays ASCII-safe
KICKER = "\u5f00\u6e90\u9879\u76ee \u00b7 \u6297\u6c61\u67d3 LLM \u4ea4\u6613 Agent \u56de\u6d4b\u73af\u5883"
TITLE1 = "Agent\u7092\u80a1"
TITLE2 = "\u8fde\u4e2a\u56de\u6d4b\u6846\u67b6"
TITLE3 = "\u90fd\u6ca1\u6709\uff1f"
SUB = "4 \u4e2a\u5927\u6a21\u578b \u00b7 \u66b4\u8dcc\u6708 \u00b7 21 \u4e2a\u4ea4\u6613\u65e5\u5b9e\u6d4b"
BADGE = "GitHub \u641c TraderHarness"

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# Bottom: pixel office, nearest-neighbor keeps the pixel-art look crisp
office = Image.open(OFFICE).convert("RGB")
scale = W / office.width
oh = int(office.height * scale)
office = office.resize((W, oh), Image.NEAREST)
# Center-crop vertically so the screenshot only fills the bottom 690px
TARGET_OH = 690
top = (oh - TARGET_OH) // 2
office = office.crop((0, top, W, top + TARGET_OH))
oh = TARGET_OH
img.paste(office, (0, H - oh))

# Fade the top of the screenshot into the dark background
fade_h = 140
for i in range(fade_h):
    alpha = 1 - i / fade_h
    y = H - oh + i
    overlay = Image.new("RGB", (W, 1), BG)
    band = img.crop((0, y, W, y + 1))
    img.paste(Image.blend(band, overlay, alpha), (0, y))
draw = ImageDraw.Draw(img)

MARGIN = 84
y = 88

kicker_f = ImageFont.truetype(BOLD, 38)
draw.text((MARGIN, y), KICKER, font=kicker_f, fill=GREEN)
y += 88

title_f = ImageFont.truetype(BOLD, 118)
draw.text((MARGIN, y), TITLE1, font=title_f, fill=WHITE)
y += 144
draw.text((MARGIN, y), TITLE2, font=title_f, fill=GREEN)
y += 144
draw.text((MARGIN, y), TITLE3, font=title_f, fill=WHITE)
y += 168

sub_f = ImageFont.truetype(REG, 40)
draw.text((MARGIN, y), SUB, font=sub_f, fill=GRAY)

# Badge pill at the bottom over the screenshot
badge_f = ImageFont.truetype(BOLD, 36)
bb = draw.textbbox((0, 0), BADGE, font=badge_f)
bw, bh = bb[2] - bb[0], bb[3] - bb[1]
pad_x, pad_y = 34, 20
bx, by = (W - bw) // 2 - pad_x, H - 96 - bh - pad_y
draw.rounded_rectangle(
    (bx, by, bx + bw + 2 * pad_x, by + bh + 2 * pad_y),
    radius=(bh + 2 * pad_y) // 2,
    fill=(10, 13, 17),
    outline=GREEN,
    width=3,
)
draw.text(((W - bw) // 2, by + pad_y - bb[1]), BADGE, font=badge_f, fill=GREEN)

img.save(OUT)
print("saved", OUT, img.size)