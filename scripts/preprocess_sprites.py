"""Pre-process pixel art sprites: remove magenta background, validate grid.

Run: .venv/Scripts/python.exe scripts/preprocess_sprites.py
"""

from pathlib import Path

from PIL import Image

ASSETS_DIR = Path(__file__).parent.parent / "assets" / "pixel-art"


def remove_magenta_bg(input_path: Path, output_path: Path, tolerance: int = 60) -> None:
    """Replace magenta (#FF00FF) background with transparency."""
    img = Image.open(input_path).convert("RGBA")
    pixels = img.load()
    w, h = img.size

    count = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if r > (255 - tolerance) and g < tolerance and b > (255 - tolerance):
                pixels[x, y] = (0, 0, 0, 0)
                count += 1

    img.save(output_path)
    total = w * h
    print(f"  Removed {count:,} magenta pixels ({count/total*100:.1f}%) → {output_path.name}")


def main() -> None:
    print("Pre-processing pixel art sprites...")
    print(f"Assets dir: {ASSETS_DIR}\n")

    trader_in = ASSETS_DIR / "trader_sprite.png"
    trader_out = ASSETS_DIR / "trader_sprite_clean.png"
    if trader_in.exists():
        print(f"Processing trader spritesheet ({trader_in.stat().st_size:,} bytes)...")
        remove_magenta_bg(trader_in, trader_out)

        img = Image.open(trader_out)
        print(f"  Dimensions: {img.size[0]}x{img.size[1]}")
        cols, rows = 4, 7
        cell_w = img.size[0] // cols
        cell_h = img.size[1] // rows
        print(f"  Grid: {cols}x{rows} → cell size {cell_w}x{cell_h}")
    else:
        print(f"  SKIP: {trader_in} not found")

    ui_in = ASSETS_DIR / "ui_elements.png"
    ui_out = ASSETS_DIR / "ui_elements_clean.png"
    if ui_in.exists():
        print(f"\nProcessing UI elements ({ui_in.stat().st_size:,} bytes)...")
        remove_magenta_bg(ui_in, ui_out)

        img = Image.open(ui_out)
        print(f"  Dimensions: {img.size[0]}x{img.size[1]}")
    else:
        print(f"  SKIP: {ui_in} not found")

    print("\nDone! Clean assets ready.")
    for f in sorted(ASSETS_DIR.glob("*_clean.png")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
