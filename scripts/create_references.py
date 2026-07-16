"""Create reference images for the V7 anchor-chain pipeline.

Outputs:
  references/pixel-grid-1024.png    — alternating pixel checkerboard (forces pixel discipline)
  references/sheet-guide-4x1.png    — 4-frame horizontal strip guide (for interactions)
  references/sheet-guide-4x4.png    — 4x4 walk cycle grid guide
  references/sheet-guide-5x2.png    — 5x2 attack/idle guide (chongdashu format)

Run: .venv/Scripts/python.exe scripts/create_references.py
"""

from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "assets" / "pixel-art" / "v7" / "references"
OUT.mkdir(parents=True, exist_ok=True)


def make_pixel_grid(size: int = 1024, cell: int = 32) -> Image.Image:
    """Alternating black/white checkerboard at cell-pixel scale."""
    img = Image.new("RGB", (size, size), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    cols = size // cell
    for row in range(cols):
        for col in range(cols):
            if (row + col) % 2 == 0:
                x0, y0 = col * cell, row * cell
                draw.rectangle([x0, y0, x0 + cell - 1, y0 + cell - 1], fill=(20, 20, 20))
    return img


def make_sheet_guide(cols: int, rows: int, cell_w: int = 256, cell_h: int = 256) -> Image.Image:
    """Sheet layout guide with numbered cells and grid lines."""
    w, h = cols * cell_w, rows * cell_h
    img = Image.new("RGB", (w, h), (40, 40, 40))
    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * cell_w, r * cell_h
            draw.rectangle([x0 + 2, y0 + 2, x0 + cell_w - 3, y0 + cell_h - 3],
                           outline=(100, 100, 100), width=2)
            frame_num = r * cols + c + 1
            draw.text((x0 + 10, y0 + 10), str(frame_num), fill=(180, 180, 180))

    # Grid lines
    for c in range(1, cols):
        draw.line([(c * cell_w, 0), (c * cell_w, h)], fill=(80, 80, 80), width=1)
    for r in range(1, rows):
        draw.line([(0, r * cell_h), (w, r * cell_h)], fill=(80, 80, 80), width=1)

    return img


def main():
    print("Creating reference images...")

    grid = make_pixel_grid(1024, 32)
    grid.save(OUT / "pixel-grid-1024.png")
    print(f"  pixel-grid-1024.png ({grid.size})")

    guide_4x1 = make_sheet_guide(4, 1)
    guide_4x1.save(OUT / "sheet-guide-4x1.png")
    print(f"  sheet-guide-4x1.png ({guide_4x1.size})")

    guide_4x4 = make_sheet_guide(4, 4)
    guide_4x4.save(OUT / "sheet-guide-4x4.png")
    print(f"  sheet-guide-4x4.png ({guide_4x4.size})")

    guide_5x2 = make_sheet_guide(5, 2)
    guide_5x2.save(OUT / "sheet-guide-5x2.png")
    print(f"  sheet-guide-5x2.png ({guide_5x2.size})")

    print("Done!")


if __name__ == "__main__":
    main()
