#!/usr/bin/env python3
"""Procedurally regenerate the pixel-office character sprite sheet.

Output: pixel-office/public/assets/characters/characters.png
Layout: 8 columns x 24 rows of 32x32 RGBA frames (256x768).

Each character owns a 6-row block (4 characters):
  block+0  DOWN    col0-1 idle(breathing)  col2-5 walk cycle
  block+1  UP      col0-1 idle             col2-5 walk cycle
  block+2  RIGHT   col0-1 idle             col2-5 walk cycle
  block+3  LEFT    col0-1 idle             col2-5 walk cycle (mirror of RIGHT)
  block+4  SIT     col0-1 UP  col2-3 DOWN  col4-5 RIGHT  col6-7 LEFT (typing)
  block+5  PRESENT col0-1 UP  col2-3 DOWN  col4-5 RIGHT  col6-7 LEFT (arm raised)

Cast (jacket colors match the agent cards):
  0 steel blue #315c78  short dark hair, light skin, GLASSES
  1 purple     #6b4f84  slicked-back auburn hair, tan skin, gold TIE
  2 ochre      #8a574d  blue-black ponytail, pale skin, red LANYARD + badge
  3 green      #3f6c5a  black buzz cut, deep skin, HEADPHONES
"""

from pathlib import Path

from PIL import Image

SPRITE = 32
COLS = 8
BLOCK_ROWS = 6
N_CHARS = 4
ROWS = BLOCK_ROWS * N_CHARS

OUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "public" / "assets" / "characters" / "characters.png"
)
PREVIEW_PATH = Path(r"D:\finharness\tmp_sprite_preview.png")

OUTLINE = (26, 21, 33, 255)          # dark plum, matches furniture outlines
PANTS = (46, 48, 64, 255)
PANTS_D = (34, 36, 50, 255)
SHOES = (58, 44, 32, 255)
SHOES_D = (40, 30, 22, 255)
SHIRT = (240, 244, 248, 255)
SHIRT_D = (200, 206, 216, 255)
EYE = (28, 28, 38, 255)
BADGE = (240, 244, 248, 255)
SHADOW = (10, 8, 14, 70)
GLASSES = (16, 16, 24, 255)
HEADPHONE = (34, 38, 48, 255)
HEADPHONE_L = (74, 84, 110, 255)


def blend(a, b, t: float):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3)) + (255,)


CHARS = [
    {  # 0 steel blue, short hair, glasses
        "jacket": (49, 92, 120, 255), "jacket_l": (72, 124, 156, 255), "jacket_d": (34, 66, 90, 255),
        "skin": (240, 200, 160, 255), "hair": (44, 36, 32, 255), "hair_l": (82, 66, 56, 255),
        "style": "short", "accessory": "glasses", "tie": None, "lanyard": None,
    },
    {  # 1 purple, slicked-back auburn, gold tie
        "jacket": (107, 79, 132, 255), "jacket_l": (134, 104, 162, 255), "jacket_d": (78, 56, 100, 255),
        "skin": (226, 178, 138, 255), "hair": (154, 92, 46, 255), "hair_l": (190, 126, 70, 255),
        "style": "slick", "accessory": None, "tie": (217, 164, 65, 255), "lanyard": None,
    },
    {  # 2 ochre, blue-black ponytail, red lanyard
        "jacket": (138, 87, 77, 255), "jacket_l": (164, 110, 98, 255), "jacket_d": (106, 64, 56, 255),
        "skin": (244, 214, 178, 255), "hair": (30, 26, 40, 255), "hair_l": (64, 56, 86, 255),
        "style": "ponytail", "accessory": None, "tie": None, "lanyard": (194, 80, 94, 255),
    },
    {  # 3 green, black buzz cut, headphones
        "jacket": (63, 108, 90, 255), "jacket_l": (86, 136, 114, 255), "jacket_d": (46, 80, 66, 255),
        "skin": (189, 133, 86, 255), "hair": (19, 19, 26, 255), "hair_l": (52, 52, 68, 255),
        "style": "buzz", "accessory": "headphones", "tie": None, "lanyard": None,
    },
]

for _ch in CHARS:
    _ch["skin_d"] = blend(_ch["skin"], (150, 90, 60), 0.28)
    _ch["blush"] = blend(_ch["skin"], (228, 110, 110), 0.30)


class Painter:
    """Draws into one 32x32 frame."""

    def __init__(self, img: Image.Image):
        self.img = img

    def px(self, x: int, y: int, c) -> None:
        if 0 <= x < SPRITE and 0 <= y < SPRITE:
            self.img.putpixel((x, y), c)

    def rect(self, x0: int, y0: int, x1: int, y1: int, c) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.px(x, y, c)

    def erase(self, x0: int, y0: int, x1: int, y1: int) -> None:
        self.rect(x0, y0, x1, y1, (0, 0, 0, 0))


# ---------------------------------------------------------------------------
# heads (head box: x 11..20, y 4..13)
# ---------------------------------------------------------------------------

def hair_cap_down(p: Painter, ch, oy: int) -> None:
    h, hl, style = ch["hair"], ch["hair_l"], ch["style"]
    if style == "buzz":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 6 + oy, h)
        p.px(11, 7 + oy, h); p.px(20, 7 + oy, h)
        p.rect(13, 5 + oy, 15, 5 + oy, hl)           # 1px sheen strands
        p.px(17, 5 + oy, hl)
    elif style == "slick":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 6 + oy, h)
        p.rect(11, 7 + oy, 12, 7 + oy, h); p.rect(19, 7 + oy, 20, 7 + oy, h)
        p.rect(12, 5 + oy, 18, 5 + oy, hl)           # swept-back sheen
        p.rect(13, 6 + oy, 16, 6 + oy, hl)
        p.px(11, 8 + oy, h); p.px(20, 8 + oy, h)
    elif style == "ponytail":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 7 + oy, h)
        p.rect(11, 8 + oy, 11, 9 + oy, h); p.rect(20, 8 + oy, 20, 9 + oy, h)
        p.rect(13, 5 + oy, 15, 6 + oy, hl)
        p.px(18, 5 + oy, hl)
        # tail peeking over the shoulder
        p.px(10, 8 + oy, h); p.px(10, 9 + oy, h)
        p.rect(10, 10 + oy, 10, 13 + oy, h)
        p.px(10, 14 + oy, h)
        p.px(10, 10 + oy, ch["lanyard"] or h)        # hair tie wraps the tail
    else:  # short
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 6 + oy, h)
        p.rect(11, 7 + oy, 12, 7 + oy, h); p.rect(19, 7 + oy, 20, 7 + oy, h)
        p.rect(12, 5 + oy, 13, 5 + oy, hl)
        p.px(15, 4 + oy, hl)
        p.px(11, 8 + oy, h); p.px(20, 8 + oy, h)


def head_down(p: Painter, ch, oy: int = 0) -> None:
    s, sd, blush = ch["skin"], ch["skin_d"], ch["blush"]
    hair_cap_down(p, ch, oy)
    # face
    p.rect(12, 7 + oy, 19, 7 + oy, s)
    p.rect(11, 8 + oy, 20, 12 + oy, s)
    p.rect(12, 13 + oy, 19, 13 + oy, sd)           # jaw shading
    p.px(11, 12 + oy, sd); p.px(20, 12 + oy, sd)
    # blush
    p.px(12, 11 + oy, blush); p.px(19, 11 + oy, blush)
    # eyebrows (skipped under glasses frames)
    if ch["accessory"] != "glasses":
        p.rect(13, 9 + oy, 14, 9 + oy, ch["hair"])
        p.rect(17, 9 + oy, 18, 9 + oy, ch["hair"])
    # eyes: 2x2 pupil + 1px catchlight
    for ex in (13, 17):
        p.rect(ex, 10 + oy, ex + 1, 11 + oy, EYE)
        p.px(ex, 10 + oy, (250, 250, 255, 255))
    p.px(15, 12 + oy, sd); p.px(16, 12 + oy, sd)   # mouth hint
    if ch["accessory"] == "glasses":
        for bx in (12, 16):                          # two lens frames
            p.rect(bx, 9 + oy, bx + 3, 9 + oy, GLASSES)
            p.rect(bx, 12 + oy, bx + 3, 12 + oy, GLASSES)
            p.px(bx, 10 + oy, GLASSES); p.px(bx, 11 + oy, GLASSES)
            p.px(bx + 3, 10 + oy, GLASSES); p.px(bx + 3, 11 + oy, GLASSES)
        p.px(11, 10 + oy, GLASSES); p.px(20, 10 + oy, GLASSES)  # temples
    elif ch["accessory"] == "headphones":
        p.rect(13, 3 + oy, 18, 3 + oy, HEADPHONE)    # band over the top
        p.rect(14, 3 + oy, 15, 3 + oy, HEADPHONE_L)
        p.rect(11, 4 + oy, 11, 8 + oy, HEADPHONE)    # side bands to the cups
        p.rect(20, 4 + oy, 20, 8 + oy, HEADPHONE)
        for cx in (9, 21):                           # ear cups
            p.rect(cx, 9 + oy, cx + 1, 11 + oy, HEADPHONE)
            p.px(cx if cx < 16 else cx + 1, 10 + oy, HEADPHONE_L)


def hair_cap_up(p: Painter, ch, oy: int) -> None:
    h, hl, style = ch["hair"], ch["hair_l"], ch["style"]
    if style == "buzz":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 8 + oy, h)
        p.rect(12, 9 + oy, 19, 9 + oy, h)
        p.rect(13, 6 + oy, 15, 7 + oy, hl)
    elif style == "slick":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 9 + oy, h)
        p.rect(13, 5 + oy, 14, 8 + oy, hl)
        p.rect(17, 5 + oy, 18, 8 + oy, hl)
    elif style == "ponytail":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 8 + oy, h)
        p.rect(12, 9 + oy, 19, 9 + oy, h)
        p.rect(13, 5 + oy, 14, 6 + oy, hl)
        # long tail down the back with a tie band and highlight strand
        p.rect(14, 9 + oy, 17, 11 + oy, h)
        p.rect(14, 12 + oy, 17, 12 + oy, ch["lanyard"] or h)
        p.rect(14, 13 + oy, 16, 15 + oy, h)
        p.rect(15, 16 + oy, 16, 16 + oy, h)
        p.rect(14, 10 + oy, 14, 11 + oy, hl)
        p.px(15, 14 + oy, hl)
    else:  # short
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(11, 5 + oy, 20, 9 + oy, h)
        p.rect(12, 5 + oy, 13, 7 + oy, hl)
        p.px(16, 5 + oy, hl)


def head_up(p: Painter, ch, oy: int = 0) -> None:
    hair_cap_up(p, ch, oy)
    s = ch["skin"]
    p.rect(13, 10 + oy, 18, 12 + oy, s)            # neck / lower head skin
    p.rect(14, 13 + oy, 17, 13 + oy, s)
    if ch["accessory"] == "headphones":
        p.rect(12, 4 + oy, 19, 4 + oy, HEADPHONE)
        for cx in (9, 21):
            p.rect(cx, 9 + oy, cx + 1, 11 + oy, HEADPHONE)


def hair_cap_right(p: Painter, ch, oy: int) -> None:
    h, hl, style = ch["hair"], ch["hair_l"], ch["style"]
    if style == "buzz":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(12, 5 + oy, 20, 6 + oy, h)
        p.px(20, 7 + oy, h)
        p.rect(13, 5 + oy, 15, 5 + oy, hl)
    elif style == "slick":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(12, 5 + oy, 20, 6 + oy, h)
        p.rect(12, 7 + oy, 13, 9 + oy, h)           # back of head
        p.rect(13, 5 + oy, 17, 5 + oy, hl)
        p.rect(14, 6 + oy, 16, 6 + oy, hl)
        p.px(20, 7 + oy, h)
    elif style == "ponytail":
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(12, 5 + oy, 20, 7 + oy, h)
        p.rect(13, 5 + oy, 14, 6 + oy, hl)
        # tail behind with tie band
        p.rect(10, 6 + oy, 12, 10 + oy, h)
        p.rect(10, 11 + oy, 11, 14 + oy, h)
        p.px(10, 15 + oy, h)
        p.rect(12, 10 + oy, 12, 10 + oy, ch["lanyard"] or h)
        p.px(11, 7 + oy, hl)
    else:  # short
        p.rect(12, 4 + oy, 19, 4 + oy, h)
        p.rect(12, 5 + oy, 20, 6 + oy, h)
        p.rect(12, 7 + oy, 12, 8 + oy, h)
        p.rect(13, 5 + oy, 14, 5 + oy, hl)
        p.px(20, 7 + oy, h)


def head_right(p: Painter, ch, oy: int = 0) -> None:
    s, sd, blush = ch["skin"], ch["skin_d"], ch["blush"]
    hair_cap_right(p, ch, oy)
    # face profile (nose pointing right)
    p.rect(13, 7 + oy, 20, 12 + oy, s)
    p.px(21, 11 + oy, s); p.px(21, 12 + oy, s)     # nose
    p.rect(14, 13 + oy, 19, 13 + oy, sd)
    p.px(19, 11 + oy, blush)
    p.rect(18, 9 + oy, 19, 9 + oy, ch["hair"])     # eyebrow
    p.rect(18, 10 + oy, 19, 11 + oy, EYE)
    p.px(18, 10 + oy, (250, 250, 255, 255))
    if ch["accessory"] == "glasses":
        p.rect(17, 9 + oy, 20, 9 + oy, GLASSES)
        p.rect(17, 12 + oy, 20, 12 + oy, GLASSES)
        p.px(20, 10 + oy, GLASSES); p.px(20, 11 + oy, GLASSES)
        p.rect(13, 10 + oy, 16, 10 + oy, GLASSES)  # temple arm
    elif ch["accessory"] == "headphones":
        p.rect(13, 4 + oy, 18, 4 + oy, HEADPHONE)
        p.rect(14, 3 + oy, 17, 3 + oy, HEADPHONE)
        p.rect(15, 9 + oy, 16, 11 + oy, HEADPHONE)  # ear cup
        p.px(16, 10 + oy, HEADPHONE_L)


# ---------------------------------------------------------------------------
# bodies
# ---------------------------------------------------------------------------

def torso_down(p: Painter, ch, oy: int, back: bool = False) -> None:
    j, jl, jd = ch["jacket"], ch["jacket_l"], ch["jacket_d"]
    p.rect(10, 14 + oy, 21, 21 + oy, j)
    p.rect(10, 14 + oy, 11, 21 + oy, jl)           # light side
    p.rect(12, 15 + oy, 12, 17 + oy, jl)
    p.rect(20, 15 + oy, 21, 21 + oy, jd)           # shade side
    p.rect(19, 20 + oy, 21, 21 + oy, jd)
    p.rect(10, 22 + oy, 21, 22 + oy, jd)           # hem
    if back:
        p.rect(13, 14 + oy, 18, 14 + oy, SHIRT)    # collar hint from behind
        p.rect(14, 15 + oy, 17, 15 + oy, SHIRT_D)
    else:
        p.rect(13, 14 + oy, 18, 14 + oy, SHIRT)    # shirt collar
        p.rect(14, 15 + oy, 17, 15 + oy, SHIRT)
        p.rect(15, 15 + oy, 16, 16 + oy, SHIRT)    # V point
        p.px(17, 15 + oy, SHIRT_D)
        if ch["tie"] is not None:
            t = ch["tie"]
            td = blend(t, (0, 0, 0), 0.3)
            p.rect(15, 16 + oy, 16, 17 + oy, td)   # knot
            p.rect(15, 18 + oy, 16, 20 + oy, t)    # body
            p.px(16, 18 + oy, td); p.px(16, 19 + oy, td)
            p.px(15, 21 + oy, t)                   # tip
        elif ch["lanyard"] is not None:
            ln = ch["lanyard"]
            p.px(14, 16 + oy, ln); p.px(17, 16 + oy, ln)
            p.px(14, 17 + oy, ln); p.px(17, 17 + oy, ln)
            p.px(15, 18 + oy, ln); p.px(16, 18 + oy, ln)
            p.rect(15, 19 + oy, 16, 21 + oy, BADGE)  # hanging badge
            p.px(15, 19 + oy, ln)
        else:
            p.rect(18, 17 + oy, 19, 18 + oy, BADGE)  # chest badge
            p.px(18, 17 + oy, ch["jacket_d"])


def arms_down(p: Painter, ch, oy: int, swing: int = 0) -> None:
    j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
    # swing: -1 left arm back/right fwd, +1 opposite, 0 neutral
    ly = oy + (-swing)
    ry = oy + swing
    for ax, ay in ((8, ly), (22, ry)):
        p.rect(ax, 14 + ay, ax + 1, 18 + ay, j)
        p.px(ax + (0 if ax < 16 else 1), 14 + ay, jd)
        p.rect(ax, 19 + ay, ax + 1, 19 + ay, SHIRT)     # shirt cuff
        p.rect(ax, 20 + ay, ax + 1, 21 + ay, s)         # hand


def legs_down(p: Painter, phase: int | None) -> None:
    """phase None = standing; 0..3 walk cycle."""
    if phase is None:
        p.rect(12, 23, 14, 27, PANTS)
        p.rect(17, 23, 19, 27, PANTS)
        p.rect(12, 23, 12, 27, PANTS_D)
        p.rect(17, 23, 17, 27, PANTS_D)
        p.rect(11, 28, 14, 29, SHOES)
        p.rect(17, 28, 20, 29, SHOES)
        p.rect(11, 29, 14, 29, SHOES_D)
        p.rect(17, 29, 20, 29, SHOES_D)
        return
    if phase in (1, 3):  # passing, legs together
        p.rect(13, 23, 15, 27, PANTS)
        p.rect(16, 23, 18, 27, PANTS)
        p.rect(12, 28, 15, 29, SHOES)
        p.rect(16, 28, 19, 29, SHOES)
        p.rect(12, 29, 15, 29, SHOES_D)
        p.rect(16, 29, 19, 29, SHOES_D)
        return
    left_fwd = phase == 0
    fx, bx = (12, 17) if left_fwd else (17, 12)
    # forward leg (toward camera: longer)
    p.rect(fx, 23, fx + 2, 27, PANTS)
    p.rect(fx - 1, 28, fx + 2, 29, SHOES)
    p.rect(fx - 1, 29, fx + 2, 29, SHOES_D)
    # back leg (lifted)
    p.rect(bx, 23, bx + 2, 25, PANTS_D)
    p.rect(bx, 26, bx + 3, 27, SHOES)


def torso_right(p: Painter, ch, oy: int, back: bool = False) -> None:
    j, jl, jd = ch["jacket"], ch["jacket_l"], ch["jacket_d"]
    p.rect(12, 14 + oy, 19, 21 + oy, j)
    p.rect(12, 14 + oy, 12, 21 + oy, jd)           # back edge
    p.rect(18, 15 + oy, 19, 21 + oy, jl)           # chest light
    p.rect(12, 22 + oy, 19, 22 + oy, jd)
    if back:
        p.rect(14, 14 + oy, 17, 14 + oy, SHIRT)
    else:
        p.rect(16, 14 + oy, 18, 14 + oy, SHIRT)    # collar V at front
        p.px(17, 15 + oy, SHIRT)
        if ch["tie"] is not None:
            t = ch["tie"]
            p.rect(17, 16 + oy, 18, 19 + oy, t)
        elif ch["lanyard"] is not None:
            p.px(16, 16 + oy, ch["lanyard"])
            p.rect(16, 17 + oy, 17, 19 + oy, BADGE)
        else:
            p.rect(15, 17 + oy, 16, 18 + oy, BADGE)


def arm_right(p: Painter, ch, oy: int, swing: int = 0) -> None:
    j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
    ay = oy + swing
    p.rect(17, 14 + ay, 19, 18 + ay, j)
    p.rect(19, 14 + ay, 19, 18 + ay, jd)
    p.rect(17, 19 + ay, 19, 19 + ay, SHIRT)        # cuff
    p.rect(17, 20 + ay, 19, 21 + ay, s)            # hand


def legs_right(p: Painter, phase: int | None) -> None:
    if phase is None:
        p.rect(13, 23, 15, 27, PANTS_D)            # far leg
        p.rect(12, 28, 15, 29, SHOES_D)
        p.rect(15, 23, 18, 27, PANTS)              # near leg
        p.rect(15, 28, 19, 29, SHOES)
        p.rect(15, 29, 19, 29, SHOES_D)
        return
    if phase in (1, 3):
        p.rect(14, 23, 17, 27, PANTS)
        p.rect(13, 28, 17, 29, SHOES)
        p.rect(13, 29, 17, 29, SHOES_D)
        return
    fwd = phase == 0
    if fwd:
        p.rect(11, 23, 13, 25, PANTS_D)            # far leg back
        p.rect(9, 26, 12, 27, SHOES_D)
        p.rect(15, 23, 18, 27, PANTS)              # near leg forward
        p.rect(16, 28, 20, 29, SHOES)
        p.rect(16, 29, 20, 29, SHOES_D)
    else:
        p.rect(17, 23, 19, 25, PANTS_D)
        p.rect(18, 26, 21, 27, SHOES_D)
        p.rect(12, 23, 15, 27, PANTS)
        p.rect(10, 28, 14, 29, SHOES)
        p.rect(10, 29, 14, 29, SHOES_D)


# ---------------------------------------------------------------------------
# pose builders
# ---------------------------------------------------------------------------

def build_standing(p: Painter, ch, view: str, phase: int | None) -> None:
    """phase None = idle frame0; -1 = idle frame1 (breath); 0..3 = walk."""
    idle_breath = phase == -1
    walk = phase is not None and phase >= 0
    bob = 1 if idle_breath else (-1 if (walk and phase in (1, 3)) else 0)
    swing = 0
    if walk:
        swing = -1 if phase == 0 else (1 if phase == 2 else 0)
    if view == "down":
        arms_down(p, ch, bob, swing)
        torso_down(p, ch, bob)
        head_down(p, ch, bob)
        legs_down(p, phase if walk else None)
    elif view == "up":
        arms_down(p, ch, bob, swing)
        torso_down(p, ch, bob, back=True)
        head_up(p, ch, bob)
        legs_down(p, phase if walk else None)
    else:  # right
        arm_right(p, ch, bob, swing)
        torso_right(p, ch, bob)
        head_right(p, ch, bob)
        legs_right(p, phase if walk else None)


def build_sit(p: Painter, ch, view: str, phase: int) -> None:
    """Seated typing. Lower body occluded by chair/desk; butt line ~y25.

    phase 0/1 alternate the typing arms (2px) plus a 1px head bob.
    """
    tap = phase % 2
    oy = 6           # whole upper body sits lower than standing
    hb = tap         # head bob on alternate frames
    if view == "up":
        j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
        p.rect(8, 14 + oy, 10, 18 + oy, j)
        p.rect(21, 14 + oy, 23, 18 + oy, j)
        p.rect(8, 14 + oy, 8, 18 + oy, jd)
        ldrop = 2 if tap == 0 else 0
        rdrop = 2 if tap == 1 else 0
        p.rect(8, 18 + oy, 10, 18 + oy, SHIRT)     # cuffs
        p.rect(21, 18 + oy, 23, 18 + oy, SHIRT)
        p.rect(8, 19 + oy + ldrop, 10, 19 + oy + ldrop, s)
        p.rect(21, 19 + oy + rdrop, 23, 19 + oy + rdrop, s)
        torso_down(p, ch, oy, back=True)
        head_up(p, ch, oy + hb)
    elif view == "down":
        j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
        torso_down(p, ch, oy)
        head_down(p, ch, oy + hb)
        # forearms reach forward (toward camera), drawn over the torso
        ldrop = 2 if tap == 0 else 0
        rdrop = 2 if tap == 1 else 0
        p.rect(9, 20 + oy, 11, 21 + oy, j)
        p.rect(20, 20 + oy, 22, 21 + oy, j)
        p.rect(9, 22 + oy, 11, 22 + oy, SHIRT)
        p.rect(20, 22 + oy, 22, 22 + oy, SHIRT)
        p.rect(9, 23 + oy + ldrop, 11, 24 + oy + ldrop, s)
        p.rect(20, 23 + oy + rdrop, 22, 24 + oy + rdrop, s)
    else:  # right
        j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
        torso_right(p, ch, oy)
        head_right(p, ch, oy + hb)
        # arm reaching forward to the desk
        drop = 2 if tap == 1 else 0
        p.rect(17, 15 + oy, 19, 18 + oy, j)
        p.rect(19, 18 + oy, 23, 19 + oy, j)        # forearm forward
        p.rect(19, 19 + oy, 23, 19 + oy, jd)
        p.rect(22, 19 + oy, 23, 19 + oy, SHIRT)    # cuff
        p.rect(22, 20 + oy + drop, 24, 21 + oy + drop, s)  # hand on keys


def build_present(p: Painter, ch, view: str, phase: int) -> None:
    """Standing, one arm raised (explaining / pointing at board)."""
    wave = phase % 2
    j, jd, s = ch["jacket"], ch["jacket_d"], ch["skin"]
    if view == "up":
        arms_down(p, ch, 0, 0)
        p.erase(22, 14, 23, 21)                    # remove lowered right arm
        torso_down(p, ch, 0, back=True)
        # raised arm with cuff
        p.rect(22, 10 - wave, 23, 15, j)
        p.rect(23, 10 - wave, 23, 15, jd)
        p.rect(22, 9 - wave, 23, 9 - wave, SHIRT)
        p.rect(22, 7 - wave, 23, 8 - wave, s)
        head_up(p, ch, 0)
        legs_down(p, None)
    elif view == "down":
        arms_down(p, ch, 0, 0)
        p.erase(22, 14, 23, 21)
        torso_down(p, ch, 0)
        p.rect(22, 10 - wave, 23, 15, j)
        p.rect(23, 10 - wave, 23, 15, jd)
        p.rect(22, 9 - wave, 23, 9 - wave, SHIRT)
        p.rect(22, 7 - wave, 23, 8 - wave, s)
        head_down(p, ch, 0)
        legs_down(p, None)
    else:  # right
        arm_right(p, ch, 0, 0)
        torso_right(p, ch, 0)
        # raised near arm pointing forward-up
        p.rect(17, 14, 19, 18, j)
        p.rect(19, 12 - wave, 23, 13 - wave, j)
        p.rect(19, 13 - wave, 23, 13 - wave, jd)
        p.rect(23, 12 - wave, 24, 13 - wave, SHIRT)
        p.rect(24, 11 - wave, 25, 13 - wave, s)
        head_right(p, ch, 0)
        legs_right(p, None)


def ground_shadow(p: Painter, sitting: bool) -> None:
    if sitting:
        p.rect(11, 26, 20, 26, SHADOW)
        p.rect(12, 27, 19, 27, SHADOW)
    else:
        p.rect(10, 29, 21, 29, SHADOW)
        p.rect(12, 30, 19, 30, SHADOW)


def outline_frame(img: Image.Image, fc: int, fr: int) -> None:
    """Add 1px dark outline on transparent pixels adjacent to opaque ones."""
    ox, oy = fc * SPRITE, fr * SPRITE
    marks: list[tuple[int, int]] = []
    for y in range(SPRITE):
        for x in range(SPRITE):
            if img.getpixel((ox + x, oy + y))[3] != 0:
                continue
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < SPRITE and 0 <= ny < SPRITE:
                    px = img.getpixel((ox + nx, oy + ny))
                    # soft shadow pixels do not create outlines
                    if px[3] == 255:
                        marks.append((x, y))
                        break
    for x, y in marks:
        img.putpixel((ox + x, oy + y), OUTLINE)


def build_sheet() -> Image.Image:
    sheet = Image.new("RGBA", (COLS * SPRITE, ROWS * SPRITE), (0, 0, 0, 0))

    for ci, ch in enumerate(CHARS):
        base = ci * BLOCK_ROWS
        for row_in_block in range(BLOCK_ROWS):
            fr = base + row_in_block
            for fc in range(COLS):
                frame = Image.new("RGBA", (SPRITE, SPRITE), (0, 0, 0, 0))
                p = Painter(frame)

                if row_in_block <= 3:
                    view = ("down", "up", "right", "left")[row_in_block]
                    if fc <= 1:
                        phase = -1 if fc == 1 else None
                    elif fc <= 5:
                        phase = fc - 2
                    else:
                        phase = None
                    src_view = "right" if view == "left" else view
                    build_standing(p, ch, src_view, phase)
                    ground_shadow(p, False)
                    if view == "left":
                        frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
                elif row_in_block == 4:  # SIT
                    view = ("up", "down", "right", "left")[fc // 2]
                    phase = fc % 2
                    src_view = "right" if view == "left" else view
                    build_sit(p, ch, src_view, phase)
                    ground_shadow(p, True)
                    if view == "left":
                        frame = frame.transpose(Image.FLIP_LEFT_RIGHT)
                else:  # PRESENT
                    view = ("up", "down", "right", "left")[fc // 2]
                    phase = fc % 2
                    src_view = "right" if view == "left" else view
                    build_present(p, ch, src_view, phase)
                    ground_shadow(p, False)
                    if view == "left":
                        frame = frame.transpose(Image.FLIP_LEFT_RIGHT)

                sheet.paste(frame, (fc * SPRITE, fr * SPRITE))

    # outline pass per frame (after flips, so outlines mirror too)
    for fr in range(ROWS):
        for fc in range(COLS):
            outline_frame(sheet, fc, fr)

    return sheet


def build_preview(sheet: Image.Image) -> Image.Image:
    """4 characters side by side: each block becomes 8 cols x 6 rows."""
    prev = Image.new("RGBA", (COLS * SPRITE * N_CHARS, BLOCK_ROWS * SPRITE), (24, 26, 34, 255))
    for ci in range(N_CHARS):
        block = sheet.crop((0, ci * BLOCK_ROWS * SPRITE, COLS * SPRITE, (ci + 1) * BLOCK_ROWS * SPRITE))
        prev.paste(block, (ci * COLS * SPRITE, 0))
    scale = 3
    prev = prev.resize((prev.width * scale, prev.height * scale), Image.NEAREST)
    return prev


def main() -> None:
    sheet = build_sheet()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT_PATH)
    preview = build_preview(sheet)
    preview.save(PREVIEW_PATH)
    print(f"wrote {OUT_PATH} ({sheet.width}x{sheet.height})")
    print(f"wrote {PREVIEW_PATH} ({preview.width}x{preview.height})")


if __name__ == "__main__":
    main()
