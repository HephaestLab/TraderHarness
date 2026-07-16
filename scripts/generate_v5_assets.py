"""V5 Asset Generation Pipeline — Consistency-first approach.

Model: gpt-image-2-all (via vectorengine.ai)
Strategy:
  Step 1: Generate style reference (full office scene)
  Step 2: Generate each furniture piece (with reference as input)
  Step 3: Generate character walk spritesheet (with reference as input)
  Step 4: Generate interaction animations (character + furniture as input)

All assets: 3/4 top-down RPG perspective, 32px tile, character 32x48.
Transparent PNG output (native alpha).

Run: .venv/Scripts/python.exe scripts/generate_v5_assets.py
"""

import base64
import time
from pathlib import Path

import httpx

API_KEY = "sk-NFPcrFauZQyQyZUacbUohpdbQVldklH2Ao6uackD7kfvjLhP"
BASE_URL = "https://api.vectorengine.ai/v1"
MODEL = "gpt-image-2-all"
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "pixel-art" / "v5"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STYLE_CORE = (
    "16-bit pixel art, 3/4 top-down RPG perspective (like Stardew Valley). "
    "Clean crisp pixels with visible pixel grid, absolutely no anti-aliasing or smoothing. "
    "Warm cozy palette: honey wood (#c8956c, #a0704c), dark purple walls (#3d2850, #2d1f3d), "
    "purple fabric (#6b3a7d, #4a2860), teal accents (#3d8b8b, #2d6b6b), "
    "amber light (#f0c060, #d4a040). "
    "Every object should look like it belongs in the same game — same pixel density, "
    "same lighting direction (top-left light source), same color temperature."
)


def gen(name: str, prompt: str, size: str = "1024x1024",
        ref_images: list[Path] | None = None) -> Path:
    """Generate image. Optionally include reference images for style consistency."""
    output_path = OUTPUT_DIR / name
    if output_path.exists():
        print(f"  [{name}] already exists, skipping")
        return output_path

    print(f"  [{name}] generating...")
    client = httpx.Client(base_url=BASE_URL, timeout=600.0)

    body: dict = {
        "model": MODEL,
        "prompt": prompt,
        "n": 1,
        "size": size,
        "output_format": "png",
        "response_format": "b64_json",
    }

    # Add reference images if provided
    if ref_images:
        valid_refs = [p for p in ref_images if p.exists()]
        if valid_refs:
            # Use the first image as input for style reference
            ref_b64 = base64.b64encode(valid_refs[0].read_bytes()).decode()
            body["image"] = ref_b64

    resp = client.post(
        "/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=body,
    )

    if resp.status_code != 200:
        print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
        return output_path

    data = resp.json()
    img_bytes = base64.b64decode(data["data"][0]["b64_json"])
    output_path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")
    return output_path


def main() -> None:
    print("=" * 60)
    print("V5 PIPELINE — Consistency-first")
    print(f"Model: {MODEL}")
    print(f"Output: {OUTPUT_DIR}")
    print("=" * 60)

    # ═══════════════════════════════════════════════════════════
    # STEP 1: Style Reference — Full office scene
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 1: Style Reference ===")

    ref_path = gen("_style_reference.png", (
        f"{STYLE_CORE}\n\n"
        "Draw a complete cozy trader's office room, 20x20 tile grid. "
        "This is a STYLE REFERENCE that all other assets will match.\n\n"
        "Room contents (all visible, clear, well-separated):\n"
        "- Dark purple brick walls surrounding the room\n"
        "- Honey-colored wooden plank floor\n"
        "- Top-left: L-shaped desk with 2 monitors (K-line chart + code), keyboard, desk lamp\n"
        "- Near desk: dark purple office chair\n"
        "- Top wall: whiteboard with sticky notes, wall clock, framed chart poster\n"
        "- Right side: tall server rack with blinking LEDs\n"
        "- Center: teal oval rug on the floor\n"
        "- Right side: dark purple sofa with cream pillow\n"
        "- Top-center: coffee station (espresso machine + mug on small table)\n"
        "- Bottom: low bookshelf with colorful books, monstera plant\n"
        "- Extras: floor lamp, water cooler, filing cabinet, small succulent\n"
        "- Large window on right wall showing city night skyline\n\n"
        "The room should feel spacious with clear walkable paths between furniture. "
        "All furniture clearly distinct and recognizable from this perspective. "
        "NO characters/people in the scene."
    ), "1536x1536")

    time.sleep(2)

    # ═══════════════════════════════════════════════════════════
    # STEP 2: Individual Furniture (with style reference)
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 2: Furniture ===")

    furniture_prompts = {
        "furniture_desk.png": (
            f"{STYLE_CORE}\n\n"
            "A single L-shaped office desk, isolated on transparent background. "
            "Warm honey wood surface with darker wood drawers. On top: two monitors "
            "(one large showing green/red K-line chart, one smaller showing blue code), "
            "RGB mechanical keyboard, mouse. Small warm desk lamp on left edge. "
            "Footprint: about 3 tiles wide x 2 tiles deep (96x64 pixels of content). "
            "PNG with transparent background."
        ),
        "furniture_chair.png": (
            f"{STYLE_CORE}\n\n"
            "A single ergonomic office chair, isolated on transparent background. "
            "Dark purple (#4a2860) seat and backrest, black metal base with 5 small wheels. "
            "Viewed from 3/4 top-down showing seat top and backrest. "
            "Footprint: 1 tile (32x32 pixels of content, but sprite is ~32x40 with backrest). "
            "PNG with transparent background."
        ),
        "furniture_coffee.png": (
            f"{STYLE_CORE}\n\n"
            "A single coffee station, isolated on transparent background. "
            "Small honey wood side table. On top: black espresso machine, white ceramic mug "
            "with tiny steam wisps, sugar jar. "
            "Footprint: about 1.5x1.5 tiles (48x48 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_sofa.png": (
            f"{STYLE_CORE}\n\n"
            "A single 2-seater sofa/couch, isolated on transparent background. "
            "Dark purple (#6b3a7d) upholstery, one cream throw pillow on left side. "
            "Viewed from 3/4 above showing cushion tops and backrest. "
            "Footprint: 2 tiles wide x 1.5 tiles deep (64x48 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_server.png": (
            f"{STYLE_CORE}\n\n"
            "A single tall server rack cabinet, isolated on transparent background. "
            "Dark metal frame (#2d1f3d) with glass front panel showing rows of small "
            "blinking LED dots (green and amber), cable routing visible. "
            "Small warning sticker. Purple LED glow at bottom. "
            "Footprint: 1 tile wide x 2.5 tiles tall (32x80 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_bookshelf.png": (
            f"{STYLE_CORE}\n\n"
            "A single low wooden bookshelf, isolated on transparent background. "
            "Warm honey wood frame, two shelf levels filled with colorful book spines "
            "(red, blue, yellow, green, purple). Small globe decoration on top-right. "
            "Footprint: 2 tiles wide x 1.5 tiles tall (64x48 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_whiteboard.png": (
            f"{STYLE_CORE}\n\n"
            "A single whiteboard on a simple metal easel, isolated on transparent background. "
            "White rectangular board with small colorful sticky notes (yellow, pink, blue) "
            "and a simple hand-drawn chart sketch in green/red. Marker tray at bottom. "
            "Footprint: 2 tiles wide x 2 tiles tall (64x64 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_plant_big.png": (
            f"{STYLE_CORE}\n\n"
            "A single potted monstera plant, isolated on transparent background. "
            "Dark ceramic pot (#3d2850), lush green monstera with 4-5 split leaves "
            "in various shades of green. "
            "Footprint: 1x1.5 tiles (32x48 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_plant_small.png": (
            f"{STYLE_CORE}\n\n"
            "A single tiny potted succulent, isolated on transparent background. "
            "Small terracotta pot with a round green succulent. Very small — about 16x20 pixels. "
            "PNG with transparent background."
        ),
        "furniture_rug.png": (
            f"{STYLE_CORE}\n\n"
            "A single oval area rug viewed from directly above (flat on floor), "
            "isolated on transparent background. Dark teal (#3d8b8b) with subtle "
            "lighter border pattern. "
            "Footprint: 4 tiles wide x 3 tiles tall (128x96 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_lamp.png": (
            f"{STYLE_CORE}\n\n"
            "A single floor lamp, isolated on transparent background. "
            "Thin dark metal stand with warm amber (#f0c060) glowing lampshade at top. "
            "Footprint: 1x2 tiles (32x64 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_filing.png": (
            f"{STYLE_CORE}\n\n"
            "A single metal filing cabinet, isolated on transparent background. "
            "Dark gray metal, 3 drawers with small handles. A few papers sticking out. "
            "Footprint: 1x1.5 tiles (32x48 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_water.png": (
            f"{STYLE_CORE}\n\n"
            "A single office water cooler, isolated on transparent background. "
            "White/light gray body with blue water bottle on top, small cup dispenser. "
            "Footprint: 1x2 tiles (32x64 pixels content). "
            "PNG with transparent background."
        ),
        "furniture_clock.png": (
            f"{STYLE_CORE}\n\n"
            "A single round wall clock, isolated on transparent background. "
            "White face, dark frame, simple hour/minute hands. "
            "Size: about 24x24 pixels content. "
            "PNG with transparent background."
        ),
        "furniture_poster.png": (
            f"{STYLE_CORE}\n\n"
            "A single framed wall poster, isolated on transparent background. "
            "Dark wood frame, inside shows a small bullish candlestick chart "
            "(green candles going up on white background). "
            "Size: about 40x32 pixels content. "
            "PNG with transparent background."
        ),
    }

    for name, prompt in furniture_prompts.items():
        gen(name, prompt, ref_images=[ref_path])
        time.sleep(1)

    # ═══════════════════════════════════════════════════════════
    # STEP 3: Character Walk Spritesheet
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 3: Character Walk ===")

    char_path = gen("character_walk.png", (
        f"{STYLE_CORE}\n\n"
        "A pixel art character SPRITESHEET on transparent background.\n\n"
        "Character design: Cute chibi male trader. Head:body ratio about 1:1.2. "
        "Short messy dark hair. Wearing dark purple hoodie (#4a2860 body, #6b3a7d highlights). "
        "Dark gray pants, small black shoes. Over-ear headphones around neck (dark with tiny red LED). "
        "Simple dot eyes and small smile. Character is 32 pixels wide x 48 pixels tall.\n\n"
        "SPRITESHEET LAYOUT: 4 columns x 4 rows, each cell exactly 48x48 pixels.\n"
        "Total image: 192x192 pixels.\n\n"
        "Row 0: Walk DOWN (facing viewer) — 4 frames of walk cycle\n"
        "Row 1: Walk UP (back to viewer) — 4 frames of walk cycle\n"
        "Row 2: Walk LEFT — 4 frames of walk cycle\n"
        "Row 3: Walk RIGHT — 4 frames of walk cycle\n\n"
        "CRITICAL: Character must be IDENTICAL in all 16 frames — same exact proportions, "
        "same colors, same head size. Only legs and arms change for walk animation. "
        "Character centered horizontally, feet at bottom of each 48x48 cell. "
        "Clear visible leg movement between frames (left-right-left-right step cycle)."
    ), "1024x1024", ref_images=[ref_path])

    time.sleep(2)

    # ═══════════════════════════════════════════════════════════
    # STEP 4: Interaction Animations
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 4: Interactions ===")

    desk_path = OUTPUT_DIR / "furniture_desk.png"
    sofa_path = OUTPUT_DIR / "furniture_sofa.png"
    coffee_path = OUTPUT_DIR / "furniture_coffee.png"
    whiteboard_path = OUTPUT_DIR / "furniture_whiteboard.png"
    server_path = OUTPUT_DIR / "furniture_server.png"
    bookshelf_path = OUTPUT_DIR / "furniture_bookshelf.png"

    CHAR_DESC = (
        "Same character from the walk spritesheet: chibi male with dark purple hoodie, "
        "dark hair, headphones around neck, 32x48 pixel proportions. "
    )

    interactions = {
        "interact_sit_type.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48 pixels). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is sitting in a chair at a desk, TYPING on keyboard. "
            "Viewed from behind (back of head visible). Hands moving on keyboard. "
            "Only the character — NO desk or chair drawn (those are separate sprites). "
            "4 frames showing typing motion: hands alternate positions on keyboard. "
            "Character seated (legs bent, not visible below seat level)."
        ),
        "interact_sit_think.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is sitting, THINKING — one hand on chin, slight head tilt. "
            "Viewed from behind/side. "
            "Only the character, no furniture. "
            "4 frames: subtle head movement and hand-on-chin pose variation."
        ),
        "interact_coffee.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is STANDING, holding a white coffee mug, sipping. "
            "Facing left (side view). "
            "Only the character holding mug, no coffee machine. "
            "4 frames: holding mug at chest → lifting to mouth → sipping → lowering."
        ),
        "interact_sofa.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is LYING DOWN / reclining, relaxed sleepy pose. "
            "Viewed from side. "
            "Only the character in lying position, no sofa drawn. "
            "4 frames: gentle breathing animation (slight chest rise/fall)."
        ),
        "interact_whiteboard.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is STANDING facing away (back view), arm raised, "
            "writing/drawing on a whiteboard with a marker. "
            "Only the character, no whiteboard drawn. "
            "4 frames: arm moving in writing motion."
        ),
        "interact_read.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is STANDING, holding an open book and reading. "
            "Facing down (toward viewer), looking down at book in hands. "
            "Only the character with book, no bookshelf. "
            "4 frames: page turning, slight head nod."
        ),
        "interact_server.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is STANDING facing away (back view), "
            "reaching toward / touching a server panel. "
            "Only the character, no server rack drawn. "
            "4 frames: reaching forward, tapping, checking, stepping back."
        ),
        "interact_celebrate.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is CELEBRATING — jumping with both arms raised, happy! "
            "Facing down (toward viewer). "
            "4 frames: crouch down → jump up with arms high → peak of jump → landing. "
            "Energetic and joyful motion."
        ),
        "interact_frustrated.png": (
            f"{STYLE_CORE}\n\n"
            "Spritesheet: 4 frames in a row (4 columns x 1 row, each cell 48x48). "
            "Total: 192x48 pixels. Transparent background.\n\n"
            f"{CHAR_DESC}"
            "The character is FRUSTRATED — both hands on head, slouched posture. "
            "Facing down (toward viewer). "
            "4 frames: head dropping into hands, slight frustrated shake/sway."
        ),
    }

    for name, prompt in interactions.items():
        gen(name, prompt, ref_images=[char_path])
        time.sleep(1)

    # ═══════════════════════════════════════════════════════════
    # STEP 5: Bubbles & Tiles
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 5: Bubbles & Tiles ===")

    gen("bubbles.png", (
        f"{STYLE_CORE}\n\n"
        "Pixel art speech/status bubble icons in a horizontal row. "
        "Transparent background.\n"
        "6 icons spaced evenly, each about 24x24 pixels. Total: ~160x28 pixels.\n\n"
        "Left to right:\n"
        "1. White thought cloud bubble (puffy rounded edges)\n"
        "2. Green dollar sign $ in a small round bubble\n"
        "3. Blue 'Zzz' text (sleep/rest)\n"
        "4. Yellow exclamation ! in triangle (alert)\n"
        "5. Cyan magnifying glass (analysis)\n"
        "6. Red down-arrow in circle (loss)\n\n"
        "Each has bold 1-2px dark outline. Bright saturated colors."
    ), ref_images=[ref_path])

    gen("tile_floor.png", (
        f"{STYLE_CORE}\n\n"
        "A single SEAMLESS 32x32 pixel tile of warm honey-colored wooden floor planks. "
        "Horizontal wood grain lines, subtle color variation between planks. "
        "The tile edges must match perfectly when repeated in a grid. "
        "Fill the ENTIRE 32x32 area — no transparency, no empty space. "
        "This is a floor tile that will be tiled/repeated to fill the room."
    ), ref_images=[ref_path])

    gen("tile_wall.png", (
        f"{STYLE_CORE}\n\n"
        "A single SEAMLESS 32x32 pixel tile of dark purple-gray brick wall. "
        "Color: #3d2850 base with slightly lighter mortar lines. "
        "The tile edges must match perfectly when repeated. "
        "Fill the ENTIRE 32x32 area — no transparency. "
        "This is a wall tile that will be tiled/repeated for room walls."
    ), ref_images=[ref_path])

    # ═══════════════════════════════════════════════════════════
    # STEP 6: Layout Reference
    # ═══════════════════════════════════════════════════════════
    print("\n=== STEP 6: Layout Reference (20x20 grid) ===")

    gen("_layout_reference.png", (
        f"{STYLE_CORE}\n\n"
        "A top-down office room layout diagram on transparent background. "
        "20x20 grid clearly visible (faint grid lines). "
        "Show furniture placement as colored rectangles/icons with labels:\n"
        "- Top-left (col 2-4, row 2-3): DESK (3x2)\n"
        "- (col 3, row 4): CHAIR (1x1)\n"
        "- Top-left wall (col 1-2, row 0-1): WHITEBOARD (2x2)\n"
        "- Top-center (col 9, row 1-2): COFFEE STATION (1x2)\n"
        "- Right (col 17, row 2-4): SERVER RACK (1x3)\n"
        "- Center (col 7-10, row 7-9): RUG (4x3)\n"
        "- Right (col 14-15, row 12-13): SOFA (2x2)\n"
        "- Bottom (col 6-7, row 16-17): BOOKSHELF (2x2)\n"
        "- Bottom-left (col 2, row 14-15): PLANT (1x2)\n"
        "- Right (col 16, row 6-7): FLOOR LAMP (1x2)\n"
        "- Left (col 1, row 6-7): FILING CABINET (1x2)\n"
        "- Top-right (col 15, row 1): WATER COOLER (1x2)\n"
        "- Wall decorations: CLOCK (col 8, row 0), POSTER (col 12, row 0)\n\n"
        "This is a planning diagram, not a pretty picture. "
        "Use simple rectangles with text labels. Grid should be clearly countable."
    ), "1024x1024")

    print(f"\n{'='*60}")
    print("V5 PIPELINE COMPLETE")
    print(f"{'='*60}")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
