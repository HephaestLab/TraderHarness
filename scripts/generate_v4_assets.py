"""V4 Asset Generation Pipeline.

Model: gpt-image-2-2026-04-21
Background: transparent (native PNG alpha)
Strategy:
  1. Generate furniture sprites (transparent bg)
  2. Generate character base sprite
  3. Generate character-furniture interaction animations (using base as reference)
  4. Generate full office layout reference image
  5. Use layout reference to define 20x20 grid placement

Run: .venv/Scripts/python.exe scripts/generate_v4_assets.py
"""

import base64
import time
from pathlib import Path

import httpx

API_KEY = "sk-NFPcrFauZQyQyZUacbUohpdbQVldklH2Ao6uackD7kfvjLhP"
BASE_URL = "https://api.vectorengine.ai/v1"
MODEL = "gpt-image-2-all"
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "pixel-art" / "v4"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STYLE = (
    "16-bit pixel art, clean crisp pixels, no anti-aliasing, no dithering. "
    "Warm cozy color palette: dark purples, warm browns, amber wood, teal/green accents. "
    "Style reference: Stardew Valley, Eastward, Unpacking game furniture. "
    "Top-down slightly elevated 30-degree perspective. "
    "Output as PNG with fully transparent background - no background color behind the object."
)


def gen(name: str, prompt: str, size: str = "1024x1024") -> Path:
    """Generate image with transparent background. Optionally pass reference images."""
    output_path = OUTPUT_DIR / name
    print(f"  [{name}] generating...")

    client = httpx.Client(base_url=BASE_URL, timeout=300.0)

    body = {
        "model": MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "output_format": "png",
        "response_format": "b64_json",
    }

    resp = client.post(
        "/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=body,
    )

    if resp.status_code != 200:
        print(f"    ERROR {resp.status_code}: {resp.text[:300]}")
        return output_path

    data = resp.json()
    item = data["data"][0]
    img_bytes = base64.b64decode(item["b64_json"])

    output_path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")
    return output_path


def main() -> None:
    print("=" * 60)
    print("V4 ASSET PIPELINE")
    print(f"Model: {MODEL}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # ═══════════════════════════════════════════
    # PHASE 1: Individual furniture sprites
    # ═══════════════════════════════════════════
    print("\n--- PHASE 1: Furniture ---")

    furniture = {
        "desk.png": (
            f"{STYLE}\n\n"
            "A single pixel art L-shaped office desk. Warm honey-colored wood with darker "
            "wood drawers. On top: two monitors (one large showing green/red candlestick chart, "
            "one smaller showing blue code), RGB mechanical keyboard, mouse, warm yellow desk lamp "
            "on left edge. Size about 96x64 pixels content area. Transparent background."
        ),
        "chair.png": (
            f"{STYLE}\n\n"
            "A single pixel art ergonomic office chair. Dark purple seat and backrest, "
            "black base with 5 wheels. Viewed from top-down angle showing seat and backrest top. "
            "Size about 32x40 pixels content area. Transparent background."
        ),
        "coffee_station.png": (
            f"{STYLE}\n\n"
            "A single pixel art small coffee station. A wooden side table with: black espresso "
            "machine, white ceramic mug with small steam wisps, sugar jar, small napkin holder. "
            "Size about 48x48 pixels content area. Transparent background."
        ),
        "sofa.png": (
            f"{STYLE}\n\n"
            "A single pixel art 2-seater couch. Dark purple/plum upholstery, one cream throw "
            "pillow on left side. Viewed from slightly above showing seat cushions and backrest top. "
            "Size about 64x48 pixels content area. Transparent background."
        ),
        "server_rack.png": (
            f"{STYLE}\n\n"
            "A single pixel art server rack cabinet. Tall, black metal with glass front panel. "
            "Rows of blinking LED dots (green and amber), cable routing visible, ventilation grilles, "
            "small warning sticker. Purple LED strip along bottom. "
            "Size about 32x80 pixels content area. Transparent background."
        ),
        "bookshelf.png": (
            f"{STYLE}\n\n"
            "A single pixel art low wooden bookshelf. Warm brown wood, two shelf levels visible "
            "filled with colorful book spines (red, blue, yellow, green, purple). Small globe "
            "decoration on top. Size about 64x48 pixels content area. Transparent background."
        ),
        "whiteboard.png": (
            f"{STYLE}\n\n"
            "A single pixel art whiteboard on a metal easel stand. White rectangular board with "
            "colorful sticky notes (yellow, pink, blue), hand-drawn chart sketches (green/red lines), "
            "marker tray at bottom with colored markers. "
            "Size about 48x64 pixels content area. Transparent background."
        ),
        "plant_monstera.png": (
            f"{STYLE}\n\n"
            "A single pixel art potted monstera plant. Dark ceramic pot, lush green monstera "
            "with 4-5 characteristic split leaves in various green shades. "
            "Size about 40x56 pixels content area. Transparent background."
        ),
        "plant_small.png": (
            f"{STYLE}\n\n"
            "A single pixel art small potted succulent. Cute terracotta pot with a round green "
            "succulent plant. Size about 20x24 pixels content area. Transparent background."
        ),
        "rug.png": (
            f"{STYLE}\n\n"
            "A single pixel art oval area rug viewed from directly above (flat on floor). "
            "Dark teal/forest green with subtle lighter border pattern. "
            "Size about 96x64 pixels content area. Transparent background."
        ),
        "lamp_floor.png": (
            f"{STYLE}\n\n"
            "A single pixel art floor lamp. Thin dark metal stand with warm amber/yellow "
            "glowing lampshade at top, casting soft light. "
            "Size about 24x64 pixels content area. Transparent background."
        ),
        "filing_cabinet.png": (
            f"{STYLE}\n\n"
            "A single pixel art metal filing cabinet. Dark gray, 3 drawers with small handles. "
            "A few papers sticking out of top drawer. "
            "Size about 32x48 pixels content area. Transparent background."
        ),
        "water_cooler.png": (
            f"{STYLE}\n\n"
            "A single pixel art office water cooler. White/light gray body with blue water "
            "bottle on top, small cup dispenser on side. "
            "Size about 24x56 pixels content area. Transparent background."
        ),
        "wall_clock.png": (
            f"{STYLE}\n\n"
            "A single pixel art round wall clock. White face, dark frame, simple hour/minute "
            "hands, small tick marks. Size about 24x24 pixels content area. Transparent background."
        ),
        "wall_poster_chart.png": (
            f"{STYLE}\n\n"
            "A single pixel art framed poster showing a candlestick chart. Dark wooden frame, "
            "white background with green/red candlesticks going upward (bullish). "
            "Size about 40x32 pixels content area. Transparent background."
        ),
    }

    furniture_paths = {}
    for name, prompt in furniture.items():
        path = gen(name, prompt)
        furniture_paths[name] = path
        time.sleep(1)

    # ═══════════════════════════════════════════
    # PHASE 2: Character base sprite
    # ═══════════════════════════════════════════
    print("\n--- PHASE 2: Character walking spritesheet ---")

    char_path = gen("character_walk.png", (
        f"{STYLE}\n\n"
        "Pixel art character spritesheet. Transparent background.\n\n"
        "Character: Cute chibi male trader. Big round head (1:1.2 head:body ratio), "
        "short messy dark hair, wearing dark purple hoodie (#533483 body, #8854d0 highlights), "
        "dark gray pants, small black shoes. Over-ear headphones around neck with tiny red LED dot. "
        "Simple dot eyes, small friendly smile. Character is about 24x32 pixels tall.\n\n"
        "LAYOUT: 4 columns x 4 rows grid, each cell 48x48 pixels. Total: 192x192 pixels.\n"
        "Row 0: Walk DOWN - 4 frames (left step, neutral, right step, neutral)\n"
        "Row 1: Walk UP (back view) - 4 frames\n"
        "Row 2: Walk LEFT - 4 frames\n"
        "Row 3: Walk RIGHT - 4 frames\n\n"
        "Each frame shows clear leg movement animation progression. "
        "Character CONSISTENT across all 16 frames — same size, same colors, same proportions. "
        "Centered in each 48x48 cell with padding around."
    ), "1024x1024")

    # ═══════════════════════════════════════════
    # PHASE 3: Character-furniture interactions
    # ═══════════════════════════════════════════
    print("\n--- PHASE 3: Interaction animations ---")

    # Use character + furniture as reference for consistent style
    interactions = {
        "char_sit_type.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader, ~24x32px) sitting in an office chair "
            "at a desk, typing on keyboard. Viewed from behind/side.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48 pixels.\n"
            "4 frames of typing animation: hands moving on keyboard, slight body lean forward. "
            "Character is seated (legs not visible below desk edge)."
        ),
        "char_sit_think.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) sitting in chair, thinking pose. "
            "One hand on chin, slight head tilt. Viewed from behind/side.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: subtle head tilt and hand-on-chin animation."
        ),
        "char_coffee.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) standing, holding and sipping coffee mug. "
            "Viewed from side.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: holding mug, lifting to mouth, sipping, lowering."
        ),
        "char_sofa.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) lying/reclining on a purple sofa, "
            "relaxed pose. Viewed from side.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: gentle breathing animation while lying down."
        ),
        "char_whiteboard.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) standing at a whiteboard, "
            "writing/drawing with a marker. Back view, arm raised.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: arm moving while writing on board."
        ),
        "char_celebrate.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) celebrating — jumping with arms raised, "
            "happy fist pump. Facing viewer.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: crouch, jump up with arms raised, peak, landing."
        ),
        "char_frustrated.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) frustrated — hands on head, "
            "slouched posture. Facing viewer.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: head dropping into hands, slight shake."
        ),
        "char_read.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) standing, holding an open book "
            "and reading. Viewed from front/side.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: page turning, slight head movement while reading."
        ),
        "char_server.png": (
            f"{STYLE}\n\n"
            "Pixel art character interaction spritesheet. Transparent background.\n"
            "Same character (purple hoodie chibi trader) standing facing a server rack, "
            "checking/touching the panel. Back/side view.\n\n"
            "LAYOUT: 4 columns x 1 row, each cell 48x48 pixels. Total: 192x48.\n"
            "4 frames: reaching toward rack, tapping, checking, stepping back."
        ),
    }

    for name, prompt in interactions.items():
        gen(name, prompt)
        time.sleep(1)

    # ═══════════════════════════════════════════
    # PHASE 4: Bubbles
    # ═══════════════════════════════════════════
    print("\n--- PHASE 4: Bubbles ---")

    gen("bubbles.png", (
        f"{STYLE}\n\n"
        "Pixel art speech bubble icons in a row. Transparent background.\n"
        "LAYOUT: 6 icons in a horizontal row, each about 32x32 pixels with spacing.\n"
        "Total image about 192x32 pixels.\n\n"
        "Icons left to right:\n"
        "1. White thought cloud bubble (puffy edges, hollow center)\n"
        "2. Green dollar sign ($) in a round speech bubble\n"
        "3. Blue 'Zzz' text floating (sleep indicator)\n"
        "4. Yellow/red exclamation mark (!) in alert triangle\n"
        "5. Cyan magnifying glass (analysis)\n"
        "6. Red broken heart or down-arrow (loss)\n\n"
        "Each icon has bold 1-2px dark outline, bright colors."
    ))

    # ═══════════════════════════════════════════
    # PHASE 5: Floor/Wall tiles
    # ═══════════════════════════════════════════
    print("\n--- PHASE 5: Tiles ---")

    gen("tile_wood_floor.png", (
        f"{STYLE}\n\n"
        "A single seamless pixel art wooden floor tile, 32x32 pixels. "
        "Warm honey-colored horizontal wood planks with subtle grain lines. "
        "Must tile seamlessly when repeated. Transparent background NOT needed for this — "
        "fill entire 32x32 area with the wood floor pattern."
    ))

    gen("tile_carpet.png", (
        f"{STYLE}\n\n"
        "A single seamless pixel art carpet tile, 32x32 pixels. "
        "Dark teal/forest green with subtle diamond pattern. "
        "Must tile seamlessly. Fill entire 32x32 area."
    ))

    gen("tile_wall.png", (
        f"{STYLE}\n\n"
        "A single seamless pixel art dark brick wall tile, 32x32 pixels. "
        "Dark purple-gray brick pattern. Must tile seamlessly. Fill entire 32x32 area."
    ))

    # ═══════════════════════════════════════════
    # PHASE 6: Office layout reference
    # ═══════════════════════════════════════════
    print("\n--- PHASE 6: Layout reference ---")

    gen("layout_reference.png", (
        f"{STYLE}\n\n"
        "A complete pixel art cozy trader's office room, viewed from top-down elevated angle. "
        "This is a REFERENCE IMAGE for room layout design. The room should be spacious.\n\n"
        "Room layout:\n"
        "- Walls surround the room (dark purple brick)\n"
        "- Large window on top-right wall showing city night skyline\n"
        "- LEFT AREA: L-shaped desk with dual monitors + chair + desk lamp\n"
        "- LEFT WALL: Whiteboard with sticky notes\n"
        "- CENTER: Open floor with oval teal rug\n"
        "- RIGHT SIDE: Server rack cabinet against wall, water cooler nearby\n"
        "- BOTTOM-RIGHT: Purple sofa with pillow\n"
        "- BOTTOM-CENTER: Low bookshelf with colorful books\n"
        "- BOTTOM-LEFT: Large monstera plant\n"
        "- TOP-CENTER: Coffee station (machine + mugs)\n"
        "- Wall decorations: clock, framed chart poster\n"
        "- Floor lamp near sofa\n\n"
        "Floor: warm honey wood planks. The room should feel spacious and lived-in. "
        "Clear walkable paths between all furniture. About 20x20 tile grid visible."
    ), "1536x1536")

    print(f"\n{'='*60}")
    print("V4 PIPELINE COMPLETE")
    print(f"{'='*60}")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
