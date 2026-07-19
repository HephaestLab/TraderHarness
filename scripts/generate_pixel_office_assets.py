"""Procedurally generate pixel-office furniture and character assets.

Everything here is drawn from scratch with Pillow primitives (rectangles,
ellipses, flat colors) — no downloaded images, no third-party art assets,
no external licenses to track. The output is fully reproducible: running
this script twice produces byte-identical PNGs.

Outputs:
  pixel-office/public/assets/furniture/<Name>.png   (one PNG per furniture type)
  pixel-office/public/assets/characters/characters.png  (32x32 frame spritesheet)

The furniture names match `FURNITURE` in webui/src/components/OfficeFloor.tsx
and the `type` values used in pixel-office/src/office/layout/defaultLayout.ts.

The character spritesheet layout matches `getSpriteFrame()` in
pixel-office/src/office/engine/characters.ts:
  - 32x32 px per frame
  - columns: direction block of 6 frames each -> DOWN=0, RIGHT=6, UP=12, LEFT=18
  - rows: one row per palette (4 palettes)
  - walk uses all 6 frames; idle uses frame 0; type/activity toggles frame 0/2

Run:
  .venv\\Scripts\\python.exe scripts/generate_pixel_office_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "pixel-office" / "public" / "assets"
FURNITURE_DIR = ASSETS_DIR / "furniture"
CHARACTERS_DIR = ASSETS_DIR / "characters"

RGBA = tuple[int, int, int, int]


def rgba(hexcode: str, alpha: int = 255) -> RGBA:
    hexcode = hexcode.lstrip("#")
    r, g, b = (int(hexcode[i : i + 2], 16) for i in (0, 2, 4))
    return (r, g, b, alpha)


# ---------------------------------------------------------------------------
# Shared warm-office palette. No purple/neon tones anywhere in the file.
# ---------------------------------------------------------------------------
WOOD_LIGHT = rgba("c8956c")
WOOD_MID = rgba("a2734a")
WOOD_DARK = rgba("7a5234")
WOOD_LEG = rgba("5a3a24")
INK = rgba("2f2013")
METAL_LIGHT = rgba("c4c8ce")
METAL_MID = rgba("92979f")
METAL_DARK = rgba("5f6470")
SCREEN_BG = rgba("171b21")
SCREEN_GLOW = rgba("63e8ad")
SCREEN_AMBER = rgba("f7b760")
PAPER = rgba("eee7d6")
PAPER_LINE = rgba("c9bd9e")
FABRIC_TEAL = rgba("3a6e6c")
FABRIC_TEAL_DARK = rgba("28524f")
FABRIC_BURGUNDY = rgba("934a44")
FABRIC_BURGUNDY_DARK = rgba("6c3530")
PLANT_GREEN = rgba("4c8046")
PLANT_GREEN_DARK = rgba("345a32")
POT_TERRA = rgba("a8603f")
POT_TERRA_DARK = rgba("7c4530")
WATER_BLUE = rgba("6cb3c7")
WATER_BLUE_DARK = rgba("468497")
CHROME = rgba("d6dadf")
BIN_GRAY = rgba("83878e")
BIN_GRAY_DARK = rgba("5f636b")


def canvas(w: int, h: int) -> Image.Image:
    return Image.new("RGBA", (w, h), (0, 0, 0, 0))


def block(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, color: RGBA) -> None:
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


def outline(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, color: RGBA = INK) -> None:
    draw.rectangle([x, y, x + w - 1, y + h - 1], outline=color, width=1)


def floor_shadow(img: Image.Image, cx: int, y: int, rw: int, rh: int) -> None:
    """A soft contact shadow to ground a furniture sprite on the floor."""
    draw = ImageDraw.Draw(img)
    draw.ellipse([cx - rw, y - rh, cx + rw, y + rh], fill=(10, 6, 3, 80))


# ---------------------------------------------------------------------------
# Furniture generators. Each returns an RGBA image. Sizes are chosen so the
# width matches the tile footprint (16px per tile) while height may extend
# below the footprint to convey vertical depth (top-left anchored, like the
# renderer expects: images are drawn from the furniture tile's top-left).
# ---------------------------------------------------------------------------


def gen_desk_2() -> Image.Image:
    w, h = 32, 34
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 16, h - 3, 14, 3)
    # desktop surface
    block(d, 1, 14, 30, 18, WOOD_MID)
    block(d, 1, 14, 30, 3, WOOD_LIGHT)
    block(d, 1, 29, 30, 3, WOOD_DARK)
    outline(d, 1, 14, 30, 18)
    # monitor
    block(d, 9, 1, 14, 10, METAL_DARK)
    block(d, 10, 2, 12, 8, SCREEN_BG)
    for i, y in enumerate(range(3, 9, 2)):
        color = SCREEN_GLOW if i % 2 == 0 else SCREEN_AMBER
        block(d, 11 + (i % 2) * 5, y, 4, 1, color)
    block(d, 14, 11, 4, 3, METAL_MID)
    outline(d, 9, 1, 14, 10)
    # keyboard + mouse
    block(d, 8, 21, 12, 4, METAL_LIGHT)
    outline(d, 8, 21, 12, 4)
    block(d, 22, 22, 3, 3, METAL_LIGHT)
    # paper stack
    block(d, 2, 20, 6, 6, PAPER)
    block(d, 2, 22, 6, 1, PAPER_LINE)
    outline(d, 2, 20, 6, 6)
    return img


def gen_boss_desk() -> Image.Image:
    w, h = 32, 38
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 16, h - 3, 15, 3)
    block(d, 0, 16, 32, 20, WOOD_DARK)
    block(d, 0, 16, 32, 3, WOOD_LIGHT)
    block(d, 0, 33, 32, 3, WOOD_LEG)
    outline(d, 0, 16, 32, 20)
    # dual monitors
    for mx in (4, 18):
        block(d, mx, 2, 10, 9, METAL_DARK)
        block(d, mx + 1, 3, 8, 6, SCREEN_BG)
        block(d, mx + 2, 5, 6, 1, SCREEN_GLOW)
        block(d, mx + 3, 11, 4, 3, METAL_MID)
        outline(d, mx, 2, 10, 9)
    # nameplate + pen holder
    block(d, 13, 27, 6, 3, PAPER)
    outline(d, 13, 27, 6, 3)
    block(d, 25, 24, 3, 6, WOOD_LEG)
    block(d, 25, 24, 3, 1, METAL_LIGHT)
    return img


def gen_chair_2() -> Image.Image:
    w, h = 16, 20
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 4, 1, 8, 9, FABRIC_TEAL)
    block(d, 4, 1, 8, 2, FABRIC_TEAL_DARK)
    outline(d, 4, 1, 8, 9)
    block(d, 3, 10, 10, 4, FABRIC_TEAL_DARK)
    outline(d, 3, 10, 10, 4)
    block(d, 7, 14, 2, 3, METAL_MID)
    block(d, 2, 17, 12, 2, METAL_DARK)
    for x in (2, 6, 11):
        block(d, x, 18, 2, 1, INK)
    return img


def gen_boss_chair() -> Image.Image:
    w, h = 18, 24
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 9, h - 2, 7, 2)
    block(d, 3, 1, 12, 13, FABRIC_BURGUNDY)
    block(d, 3, 1, 12, 3, FABRIC_BURGUNDY_DARK)
    outline(d, 3, 1, 12, 13)
    block(d, 2, 14, 14, 4, FABRIC_BURGUNDY_DARK)
    outline(d, 2, 14, 14, 4)
    block(d, 8, 18, 2, 3, METAL_MID)
    block(d, 1, 21, 16, 2, METAL_DARK)
    for x in (1, 6, 11, 15):
        block(d, x, 22, 2, 1, INK)
    return img


def gen_small_plant() -> Image.Image:
    w, h = 16, 26
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    d.polygon([(3, 6), (13, 6), (11, 20), (5, 20)], fill=POT_TERRA)
    block(d, 3, 6, 10, 2, POT_TERRA_DARK)
    outline(d, 3, 6, 10, 14)
    for cx, cy, r in [(8, 6, 6), (4, 9, 4), (12, 9, 4), (5, 3, 3), (11, 3, 3)]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLANT_GREEN)
    for cx, cy, r in [(8, 4, 2), (5, 7, 2), (11, 7, 2)]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=PLANT_GREEN_DARK)
    return img


def gen_big_round_table() -> Image.Image:
    w, h = 32, 32
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 16, 28, 14, 3)
    d.ellipse([1, 3, 30, 28], fill=WOOD_DARK, outline=INK, width=1)
    d.ellipse([3, 4, 28, 26], fill=WOOD_MID)
    d.ellipse([5, 5, 26, 22], fill=WOOD_LIGHT)
    # papers + laptop scattered on the table
    block(d, 12, 11, 8, 6, METAL_DARK)
    block(d, 13, 12, 6, 4, SCREEN_BG)
    block(d, 14, 13, 4, 1, SCREEN_GLOW)
    block(d, 6, 15, 5, 4, PAPER)
    outline(d, 6, 15, 5, 4)
    block(d, 21, 16, 5, 4, PAPER)
    outline(d, 21, 16, 5, 4)
    return img


def gen_water_dispenser() -> Image.Image:
    w, h = 16, 34
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    d.ellipse([2, 1, 14, 13], fill=WATER_BLUE)
    d.ellipse([3, 2, 13, 12], fill=WATER_BLUE_DARK, outline=None)
    d.ellipse([4, 3, 12, 8], fill=WATER_BLUE)
    outline(d, 2, 1, 12, 13)
    block(d, 3, 14, 10, 15, METAL_LIGHT)
    block(d, 3, 14, 10, 3, METAL_MID)
    outline(d, 3, 14, 10, 15)
    block(d, 5, 20, 6, 4, METAL_DARK)
    block(d, 6, 21, 1, 2, SCREEN_GLOW)
    block(d, 9, 21, 1, 2, SCREEN_GLOW)
    block(d, 2, 29, 12, 3, METAL_DARK)
    return img


def gen_coffee_machine() -> Image.Image:
    w, h = 16, 22
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 2, 15, 12, 4, WOOD_MID)
    outline(d, 2, 15, 12, 4)
    block(d, 3, 3, 10, 12, METAL_DARK)
    outline(d, 3, 3, 10, 12)
    block(d, 5, 5, 6, 3, METAL_MID)
    block(d, 6, 8, 1, 2, SCREEN_AMBER)
    block(d, 9, 8, 1, 2, SCREEN_GLOW)
    block(d, 6, 12, 4, 3, PAPER)
    return img


def gen_big_office_printer() -> Image.Image:
    w, h = 16, 34
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 1, 12, 14, 20, METAL_MID)
    block(d, 1, 12, 14, 4, METAL_LIGHT)
    outline(d, 1, 12, 14, 20)
    block(d, 3, 18, 10, 6, METAL_DARK)
    outline(d, 3, 18, 10, 6)
    block(d, 4, 26, 8, 2, PAPER)
    block(d, 2, 3, 12, 9, METAL_LIGHT)
    outline(d, 2, 3, 12, 9)
    block(d, 4, 5, 8, 4, PAPER)
    block(d, 12, 14, 2, 1, SCREEN_GLOW)
    return img


def gen_filing_cabinet_small() -> Image.Image:
    w, h = 16, 22
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 1, 1, 14, 20, METAL_MID)
    outline(d, 1, 1, 14, 20)
    for y in (4, 12):
        block(d, 3, y, 10, 6, METAL_DARK)
        outline(d, 3, y, 10, 6)
        block(d, 7, y + 2, 3, 2, METAL_LIGHT)
    return img


def gen_big_filing_cabinet() -> Image.Image:
    w, h = 16, 34
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 1, 1, 14, 32, METAL_MID)
    outline(d, 1, 1, 14, 32)
    for y in (3, 12, 21):
        block(d, 3, y, 10, 7, METAL_DARK)
        outline(d, 3, y, 10, 7)
        block(d, 7, y + 3, 3, 2, METAL_LIGHT)
    return img


def gen_filing_cabinet_tall() -> Image.Image:
    w, h = 16, 40
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 1, 1, 14, 38, METAL_DARK)
    outline(d, 1, 1, 14, 38)
    for y in (3, 12, 21, 30):
        block(d, 3, y, 10, 7, METAL_MID)
        outline(d, 3, y, 10, 7)
        block(d, 7, y + 3, 3, 2, METAL_LIGHT)
    return img


def gen_bin() -> Image.Image:
    w, h = 14, 16
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 7, h - 2, 5, 2)
    d.polygon([(2, 3), (12, 3), (10, 15), (4, 15)], fill=BIN_GRAY)
    d.polygon([(2, 3), (12, 3), (10, 15), (4, 15)], outline=INK)
    block(d, 1, 1, 12, 3, BIN_GRAY_DARK)
    outline(d, 1, 1, 12, 3)
    return img


def gen_board() -> Image.Image:
    w, h = 32, 22
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    block(d, 1, 1, 30, 20, WOOD_MID)
    block(d, 3, 3, 26, 16, PAPER)
    outline(d, 1, 1, 30, 20)
    outline(d, 3, 3, 26, 16, PAPER_LINE)
    notes = [
        (6, 6, SCREEN_AMBER), (14, 6, FABRIC_BURGUNDY), (22, 6, SCREEN_GLOW),
        (6, 13, SCREEN_GLOW), (14, 13, SCREEN_AMBER), (22, 13, FABRIC_BURGUNDY),
    ]
    for x, y, color in notes:
        block(d, x, y, 5, 5, color)
        outline(d, x, y, 5, 5)
    return img


def gen_wall_graph() -> Image.Image:
    w, h = 32, 20
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    block(d, 1, 1, 30, 18, SCREEN_BG)
    outline(d, 1, 1, 30, 18, METAL_MID)
    d.line([(3, 15), (3, 3)], fill=PAPER_LINE, width=1)
    d.line([(3, 15), (29, 15)], fill=PAPER_LINE, width=1)
    points = [(4, 13), (8, 10), (12, 12), (16, 6), (20, 9), (24, 5), (28, 8)]
    d.line(points, fill=SCREEN_GLOW, width=1)
    for px, py in points:
        block(d, px - 1, py - 1, 2, 2, SCREEN_AMBER)
    return img


def gen_bookshelf() -> Image.Image:
    w, h = 32, 34
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 16, h - 3, 14, 3)
    block(d, 1, 1, 30, 32, WOOD_DARK)
    outline(d, 1, 1, 30, 32)
    book_colors = [SCREEN_AMBER, FABRIC_BURGUNDY, SCREEN_GLOW, WATER_BLUE, PAPER]
    for shelf_y in (4, 15, 26):
        block(d, 3, shelf_y + 7, 26, 2, WOOD_MID)
        x = 4
        i = 0
        while x < 27:
            bw = 3 if i % 3 else 4
            block(d, x, shelf_y, bw, 7, book_colors[i % len(book_colors)])
            x += bw + 1
            i += 1
    return img


def gen_small_sofa() -> Image.Image:
    w, h = 32, 24
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 16, h - 2, 14, 2)
    block(d, 1, 6, 30, 15, FABRIC_TEAL)
    block(d, 1, 6, 30, 3, FABRIC_TEAL_DARK)
    outline(d, 1, 6, 30, 15)
    block(d, 1, 6, 4, 15, FABRIC_TEAL_DARK)
    block(d, 27, 6, 4, 15, FABRIC_TEAL_DARK)
    block(d, 8, 10, 7, 6, PAPER)
    outline(d, 8, 10, 7, 6)
    for x in (2, 28):
        block(d, x, 20, 2, 3, WOOD_LEG)
    return img


def gen_small_table() -> Image.Image:
    w, h = 16, 16
    img = canvas(w, h)
    d = ImageDraw.Draw(img)
    floor_shadow(img, 8, h - 2, 6, 2)
    block(d, 1, 2, 14, 6, WOOD_LIGHT)
    block(d, 1, 2, 14, 2, WOOD_MID)
    outline(d, 1, 2, 14, 6)
    for x in (2, 11):
        block(d, x, 8, 3, 6, WOOD_LEG)
    block(d, 4, 3, 4, 3, PAPER)
    return img


FURNITURE_GENERATORS = {
    "Desk-2": gen_desk_2,
    "Chair-2": gen_chair_2,
    "Small-Plant": gen_small_plant,
    "Big-Round-Table": gen_big_round_table,
    "Boss-Desk": gen_boss_desk,
    "Boss-Chair": gen_boss_chair,
    "Big-Office-Printer": gen_big_office_printer,
    "Water-Dispenser": gen_water_dispenser,
    "Filing-Cabinet-Small": gen_filing_cabinet_small,
    "Bin": gen_bin,
    "Wall-Graph": gen_wall_graph,
    "Board": gen_board,
    "Coffee-Machine": gen_coffee_machine,
    "Big-Filing-Cabinet": gen_big_filing_cabinet,
    "Filing-Cabinet-Tall": gen_filing_cabinet_tall,
    "Bookshelf": gen_bookshelf,
    "Small-Sofa": gen_small_sofa,
    "Small-Table": gen_small_table,
}


# ---------------------------------------------------------------------------
# Characters. 32x32 frames, 4 palettes, 4 directions x 6 frames.
# No purple/neon tones — four readable, distinct business-casual palettes.
# ---------------------------------------------------------------------------

SPRITE_SIZE = 32
FRAMES_PER_DIR = 6
DIRECTIONS = ["DOWN", "RIGHT", "UP", "LEFT"]

PALETTES = [
    {  # analyst blue
        "skin": rgba("f0c498"),
        "hair": rgba("4a3226"),
        "top": rgba("34486e"),
        "top_dk": rgba("263652"),
        "pants": rgba("343a46"),
    },
    {  # quant green
        "skin": rgba("d8a47c"),
        "hair": rgba("28221c"),
        "top": rgba("3a6e56"),
        "top_dk": rgba("2a5440"),
        "pants": rgba("2c322e"),
    },
    {  # risk burgundy
        "skin": rgba("c68c66"),
        "hair": rgba("1c1816"),
        "top": rgba("8c443a"),
        "top_dk": rgba("68302a"),
        "pants": rgba("32302e"),
    },
    {  # trader amber
        "skin": rgba("e8bc94"),
        "hair": rgba("9c6e3a"),
        "top": rgba("bc8c3a"),
        "top_dk": rgba("966a28"),
        "pants": rgba("36322c"),
    },
]

# pose sequence reused for both walk cycle (all 6) and type/activity toggle (0, 2)
POSES = ["neutral", "strideA", "tap", "strideB", "neutral", "strideA"]


def _shadow(d: ImageDraw.ImageDraw) -> None:
    d.ellipse([9, 28, 23, 31], fill=(10, 6, 3, 70))


def _legs(d: ImageDraw.ImageDraw, pose: str, pants: RGBA) -> None:
    left_x, right_x = 12, 18
    y0 = 23
    if pose == "strideA":
        left_y, right_y = y0, y0 + 1
        right_x += 1
    elif pose == "strideB":
        left_y, right_y = y0 + 1, y0
        left_x -= 1
    else:
        left_y, right_y = y0, y0
    block(d, left_x, left_y, 3, 6, pants)
    block(d, right_x, right_y, 3, 6, pants)
    block(d, left_x, left_y + 5, 3, 1, INK)
    block(d, right_x, right_y + 5, 3, 1, INK)


def _draw_down(pose: str, palette: dict) -> Image.Image:
    img = canvas(SPRITE_SIZE, SPRITE_SIZE)
    d = ImageDraw.Draw(img)
    _shadow(d)
    _legs(d, pose, palette["pants"])
    torso_y = 12
    block(d, 9, torso_y, 14, 10, palette["top"])
    block(d, 9, torso_y, 1, 10, palette["top_dk"])
    block(d, 22, torso_y, 1, 10, palette["top_dk"])
    block(d, 15, torso_y, 2, 10, palette["top_dk"])
    # arms
    arm_lift = 1 if pose == "tap" else 0
    fwd = 1 if pose == "strideA" else (-1 if pose == "strideB" else 0)
    block(d, 6 - fwd, 14 - arm_lift, 3, 7, palette["top_dk"])
    block(d, 6 - fwd, 19 - arm_lift, 3, 2, palette["skin"])
    block(d, 23 + fwd, 14 + arm_lift, 3, 7, palette["top_dk"])
    block(d, 23 + fwd, 19 + arm_lift, 3, 2, palette["skin"])
    # head
    block(d, 11, 3, 10, 10, palette["skin"])
    block(d, 10, 2, 12, 4, palette["hair"])
    block(d, 10, 5, 2, 5, palette["hair"])
    block(d, 20, 5, 2, 5, palette["hair"])
    block(d, 13, 9, 2, 2, INK)
    block(d, 17, 9, 2, 2, INK)
    outline(d, 9, torso_y, 14, 10)
    outline(d, 11, 3, 10, 10)
    return img


def _draw_up(pose: str, palette: dict) -> Image.Image:
    img = canvas(SPRITE_SIZE, SPRITE_SIZE)
    d = ImageDraw.Draw(img)
    _shadow(d)
    _legs(d, pose, palette["pants"])
    torso_y = 12
    block(d, 9, torso_y, 14, 10, palette["top_dk"])
    block(d, 9, torso_y, 1, 10, palette["top"])
    block(d, 22, torso_y, 1, 10, palette["top"])
    block(d, 13, torso_y, 6, 3, palette["top"])
    arm_lift = 1 if pose == "tap" else 0
    fwd = 1 if pose == "strideA" else (-1 if pose == "strideB" else 0)
    block(d, 6 - fwd, 14 - arm_lift, 3, 7, palette["top_dk"])
    block(d, 23 + fwd, 14 + arm_lift, 3, 7, palette["top_dk"])
    block(d, 11, 3, 10, 10, palette["hair"])
    block(d, 13, 3, 6, 3, palette["hair"])
    outline(d, 9, torso_y, 14, 10)
    outline(d, 11, 3, 10, 10)
    return img


def _draw_right(pose: str, palette: dict) -> Image.Image:
    img = canvas(SPRITE_SIZE, SPRITE_SIZE)
    d = ImageDraw.Draw(img)
    _shadow(d)
    front_x, back_x = 17, 13
    y0 = 23
    if pose == "strideA":
        front_y, back_y = y0 + 1, y0
        front_x += 1
    elif pose == "strideB":
        front_y, back_y = y0, y0 + 1
        back_x -= 1
    else:
        front_y, back_y = y0, y0
    block(d, back_x, back_y, 3, 6, palette["pants"])
    block(d, front_x, front_y, 3, 6, palette["pants"])
    block(d, back_x, back_y + 5, 3, 1, INK)
    block(d, front_x, front_y + 5, 3, 1, INK)
    # torso (slightly narrower, offset toward facing side)
    torso_y = 12
    block(d, 11, torso_y, 12, 10, palette["top"])
    block(d, 11, torso_y, 3, 10, palette["top_dk"])
    outline(d, 11, torso_y, 12, 10)
    # near arm rendered in front of torso on the facing side
    arm_lift = 1 if pose == "tap" else 0
    fwd = 1 if pose == "strideA" else (-1 if pose == "strideB" else 0)
    block(d, 20 + fwd, 14 - arm_lift, 3, 7, palette["top_dk"])
    block(d, 20 + fwd, 19 - arm_lift, 3, 2, palette["skin"])
    # head, profile: hair sweeps back (left), face toward facing side (right)
    block(d, 12, 3, 9, 10, palette["skin"])
    block(d, 11, 2, 9, 4, palette["hair"])
    block(d, 11, 5, 3, 6, palette["hair"])
    block(d, 18, 9, 2, 2, INK)
    outline(d, 12, 3, 9, 10)
    return img


def _sheet_frame(direction: str, pose_index: int, palette: dict) -> Image.Image:
    pose = POSES[pose_index]
    if direction == "DOWN":
        return _draw_down(pose, palette)
    if direction == "UP":
        return _draw_up(pose, palette)
    if direction == "RIGHT":
        return _draw_right(pose, palette)
    if direction == "LEFT":
        return ImageOps.mirror(_draw_right(pose, palette))
    raise ValueError(direction)


def gen_character_sheet() -> Image.Image:
    cols = len(DIRECTIONS) * FRAMES_PER_DIR
    rows = len(PALETTES)
    sheet = Image.new("RGBA", (cols * SPRITE_SIZE, rows * SPRITE_SIZE), (0, 0, 0, 0))
    for row, palette in enumerate(PALETTES):
        for dir_index, direction in enumerate(DIRECTIONS):
            for frame in range(FRAMES_PER_DIR):
                frame_img = _sheet_frame(direction, frame, palette)
                col = dir_index * FRAMES_PER_DIR + frame
                sheet.paste(frame_img, (col * SPRITE_SIZE, row * SPRITE_SIZE), frame_img)
    return sheet


def main() -> None:
    FURNITURE_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    for name, generator in FURNITURE_GENERATORS.items():
        img = generator()
        path = FURNITURE_DIR / f"{name}.png"
        img.save(path)
        written.append(path)

    sheet = gen_character_sheet()
    sheet_path = CHARACTERS_DIR / "characters.png"
    sheet.save(sheet_path)
    written.append(sheet_path)

    print(f"Generated {len(written)} files:")
    for path in written:
        size = path.stat().st_size
        print(f"  {path.relative_to(ROOT)}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
