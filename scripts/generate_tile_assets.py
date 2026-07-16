"""Generate individual tile-based assets for the trader room.

Generates: tiles, individual furniture sprites, character spritesheet, bubbles.
Each furniture piece is a separate image for independent placement.

Run: .venv/Scripts/python.exe scripts/generate_tile_assets.py
"""

import base64
import time
from pathlib import Path

import httpx

API_KEY = "sk-52f492dba72b382a0661523b7ed7c83b7787bce0931408cf47ff497492b059eb"
BASE_URL = "https://vip.auto-code.net"
MODEL = "gpt-image-1"
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "pixel-art" / "v3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def gen(name: str, prompt: str, size: str = "1024x1024") -> None:
    output_path = OUTPUT_DIR / name
    print(f"\n  Generating: {name} ({size})...")

    client = httpx.Client(base_url=BASE_URL, timeout=300.0)
    resp = client.post(
        "/v1/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": MODEL,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "response_format": "b64_json",
        },
    )

    if resp.status_code != 200:
        print(f"    ERROR: {resp.status_code} - {resp.text[:200]}")
        return

    data = resp.json()
    img_bytes = base64.b64decode(data["data"][0]["b64_json"])
    output_path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")


STYLE = (
    "16-bit pixel art style, clean crisp pixels, NO anti-aliasing, "
    "warm cozy color palette (dark purples, warm browns, amber, teal accents). "
    "Solid magenta (#FF00FF) background for transparency keying. "
    "Style like Stardew Valley or Eastward indoor furniture. "
    "Viewed from slightly elevated top-down perspective (about 30 degrees)."
)


def main() -> None:
    print("=" * 60)
    print("Generating tile-based assets for V3 scene")
    print("=" * 60)

    # --- 1. Floor & Wall Tiles ---
    gen("tiles.png", (
        f"A pixel art tileset spritesheet. {STYLE}\n\n"
        "Image size: 128x64 pixels total. Grid: 4 columns x 2 rows, each cell 32x32 pixels.\n\n"
        "Row 0 (floor tiles):\n"
        "- Cell 0,0: Warm honey-colored wooden plank floor tile, horizontal grain\n"
        "- Cell 1,0: Same wood floor, slightly different plank alignment (variation)\n"
        "- Cell 2,0: Dark teal/green carpet tile with subtle diamond pattern\n"
        "- Cell 3,0: Same carpet, slight color variation\n\n"
        "Row 1 (wall tiles):\n"
        "- Cell 0,1: Dark purple-gray brick wall tile\n"
        "- Cell 1,1: Same brick with wood wainscoting on bottom half\n"
        "- Cell 2,1: Brick wall with a small window showing night city lights\n"
        "- Cell 3,1: Brick wall with a small wooden shelf\n\n"
        "IMPORTANT: Each 32x32 tile must seamlessly tile with its neighbors when repeated. "
        "Clean pixel art, solid colors, visible pixel grid. "
        "Background outside the tiles should be magenta #FF00FF."
    ), "1024x1024")

    # --- 2. Furniture (individual pieces) ---
    gen("desk.png", (
        f"A single pixel art L-shaped office desk with dual monitors. {STYLE}\n\n"
        "Viewed from top-down 30-degree angle. The desk is wooden (warm brown/amber), "
        "L-shaped. On top: two monitors (one large landscape showing green K-line chart, "
        "one smaller portrait showing blue code), a mechanical keyboard with RGB lighting, "
        "a mouse, and a warm yellow desk lamp on the left edge.\n\n"
        "Total sprite size should fill about 96x64 pixels (3 tiles wide, 2 tiles tall) "
        "centered in the image. The desk surface should be clearly visible.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("chair.png", (
        f"A single pixel art ergonomic office chair. {STYLE}\n\n"
        "Dark purple/black modern office chair with armrests, viewed from top-down 30-degree "
        "angle (we see the seat and backrest from above-behind). Wheels visible at bottom.\n\n"
        "Sprite should be about 32x48 pixels (1 tile wide, 1.5 tiles tall) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("coffee_machine.png", (
        f"A single pixel art coffee station. {STYLE}\n\n"
        "A small wooden side table with: a modern black/silver coffee machine on top, "
        "a white coffee mug with steam wisps, and a small jar of sugar. "
        "Viewed from top-down 30-degree angle.\n\n"
        "Sprite about 32x48 pixels centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("sofa.png", (
        f"A single pixel art comfortable couch/sofa. {STYLE}\n\n"
        "A dark purple/plum 2-seater sofa with one light cream throw pillow. "
        "Viewed from top-down 30-degree angle (we see the top of the backrest and seat cushions). "
        "Cozy and inviting looking.\n\n"
        "Sprite about 64x48 pixels (2 tiles wide) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("server_rack.png", (
        f"A single pixel art server rack cabinet. {STYLE}\n\n"
        "A tall black/dark gray server rack with glass front panel. Inside visible: "
        "rows of blinking LED dots (green and red/amber), cable management, ventilation slots. "
        "Small warning sticker on the side. Purple-pink LED strip along bottom edge.\n"
        "Viewed from top-down 30-degree angle.\n\n"
        "Sprite about 32x64 pixels (1 tile wide, 2 tiles tall) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("bookshelf.png", (
        f"A single pixel art low bookshelf. {STYLE}\n\n"
        "A waist-height wooden bookshelf with colorful book spines visible (red, blue, "
        "yellow, green, purple books). A small globe or decorative item on top. "
        "Viewed from top-down 30-degree angle.\n\n"
        "Sprite about 64x48 pixels (2 tiles wide) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("whiteboard.png", (
        f"A single pixel art whiteboard on a small easel/stand. {STYLE}\n\n"
        "A white rectangular board on a simple stand, with colorful sticky notes "
        "(yellow, pink, blue), hand-drawn chart diagrams (simple K-line sketch in green/red), "
        "and a small marker tray at bottom. Viewed from top-down 30-degree angle.\n\n"
        "Sprite about 64x64 pixels (2x2 tiles) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("plant.png", (
        f"A single pixel art potted monstera plant. {STYLE}\n\n"
        "A dark gray/brown pot with a lush green monstera plant. Big characteristic "
        "split leaves in various shades of green. Viewed from top-down 30-degree angle.\n\n"
        "Sprite about 32x48 pixels centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    gen("rug.png", (
        f"A single pixel art oval area rug. {STYLE}\n\n"
        "A cozy dark teal/green oval rug with a subtle geometric border pattern "
        "(slightly lighter teal edge). Viewed from directly above (flat on floor).\n\n"
        "Sprite about 96x64 pixels (3x2 tiles) centered in image.\n"
        "Solid magenta (#FF00FF) background."
    ), "1024x1024")

    # --- 3. Character Spritesheet ---
    gen("character.png", (
        f"Pixel art character spritesheet for a top-down 2D game. {STYLE}\n\n"
        "Character: Cute chibi young male trader. Big round head, short dark hair, "
        "wearing purple hoodie (#533483), dark pants, small shoes. Over-ear headphones "
        "around neck with tiny red LED. Simple dot eyes, friendly face.\n\n"
        "SPRITESHEET on magenta (#FF00FF) background:\n"
        "Total: 192x128 pixels (6 columns x 4 rows, each cell 32x32).\n\n"
        "Row 0: Walk DOWN 4 frames (left-step, stand, right-step, stand) + stand_down 2 frames\n"
        "Row 1: Walk UP 4 frames + stand_up 2 frames\n"
        "Row 2: Walk LEFT 4 frames + walk_RIGHT 2 frames\n"
        "Row 3: Sit typing (side view) 2 frames + sit thinking 2 frames + celebrate (jump) 2 frames\n\n"
        "Character is about 20x28 pixels within each 32x32 cell, centered at bottom.\n"
        "MUST be consistent across all frames — same proportions, same colors.\n"
        "Clear animation differences between frames (visible leg/arm movement)."
    ), "1024x1024")

    # --- 4. Bubbles ---
    gen("bubbles.png", (
        f"Pixel art speech bubble icons spritesheet. {STYLE}\n\n"
        "Total: 160x32 pixels (5 columns x 1 row, each cell 32x32).\n\n"
        "Each is a small bubble/icon about 20x20 pixels centered in cell:\n"
        "- Cell 0: White thought cloud bubble (bumpy circular edges, hollow inside)\n"
        "- Cell 1: Green dollar sign ($) in a small circle\n"
        "- Cell 2: Blue 'Zzz' text (sleep indicator)\n"
        "- Cell 3: Red/yellow exclamation mark (!) in triangle\n"
        "- Cell 4: Cyan magnifying glass (analysis)\n\n"
        "Bold 1-2px dark outlines, bright colors, clean and readable at small size.\n"
        "Magenta (#FF00FF) background."
    ), "1024x1024")

    print(f"\n{'='*60}")
    print("All V3 assets generated!")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
