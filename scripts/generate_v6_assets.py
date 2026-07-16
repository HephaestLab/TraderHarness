"""V6 Asset Pipeline — Dependency-tree generation with strict pixel spec.

Core rules:
  - ALL assets are 32px grid (1 tile = 32x32 pixels)
  - ALL perspectives: front-facing 45° top-down RPG
  - Generation follows dependency tree: parent images passed as input
  - Model: gemini-3.1-flash-image-preview via Google AI
  - Native transparent PNG output

Run: .venv/Scripts/python.exe scripts/generate_v6_assets.py
"""

import base64
import os
import time
from pathlib import Path

import httpx

API_KEY = "sk-NFPcrFauZQyQyZUacbUohpdbQVldklH2Ao6uackD7kfvjLhP"
BASE_URL = "https://api.vectorengine.ai/v1"
MODEL = "gemini-3.1-flash-image-preview"
OUT = Path(__file__).parent.parent / "assets" / "pixel-art" / "v6"
OUT.mkdir(parents=True, exist_ok=True)

# Mandatory prefix for EVERY prompt
PIXEL_SPEC = (
    "STYLE: 16-bit pixel art, exactly like Stardew Valley / Habitica. "
    "GRID: 1 tile = 32×32 pixels. Every element snaps to this grid. "
    "PERSPECTIVE: top-down 3/4 view (floor visible, front face of objects visible). "
    "NOT isometric. NOT side-view. NOT bird's-eye. "
    "RENDERING: Each pixel is one solid flat color. Hard edges only. "
    "NO anti-aliasing, NO dithering, NO gradients, NO glow, NO blur, NO soft shadows. "
    "OUTLINE: 1px black (#1a1a2e) outline on all sprites. "
    "PALETTE (strict): "
    "wood-light #c8956c, wood-dark #8b5e3c, "
    "wall-purple #3d2850, wall-highlight #4a3060, "
    "cloth-dark #4a2860, cloth-mid #6b3a7d, "
    "teal #3d8b8b, skin #f0c890, hair #2d1f3d, "
    "warm-light #f0c060, screen-cyan #40d0d0, "
    "black #1a1a2e, white #f5f5f0. "
    "BACKGROUND: transparent (alpha=0) unless stated otherwise. "
)

# Character identity lock — repeated in every character prompt
CHAR_LOCK = (
    "CHARACTER SPEC (do NOT deviate): "
    "Chibi male, 32px wide × 48px tall. "
    "Head = 20px tall (large round, 60% of width). "
    "Body = 28px tall (short stubby torso + legs). "
    "Hair: messy dark purple #2d1f3d, covers forehead. "
    "Face: 2 black dot eyes (2px each), 4px apart, on row 14 from top. No nose. 2px smile. "
    "Skin: #f0c890 (peach). "
    "Outfit: dark purple hoodie #4a2860 (body), lighter purple #6b3a7d (hood/sleeves). "
    "Pants: dark gray #2d2d3d. Shoes: black #1a1a2e, 2px tall. "
    "Headphones: thin dark band over hair, tiny red LED dot on right ear. "
    "PROPORTIONS: head is 40% of total height. Arms hang to hip level. "
    "This is a FIXED design. Every frame must be pixel-identical in colors and proportions. "
)


def gen(name: str, prompt: str, size: str = "1024x1024",
        inputs: list[Path] | None = None) -> Path:
    """Generate asset. Pass parent dependency images as inputs for consistency."""
    path = OUT / name
    if path.exists():
        print(f"  [{name}] exists, skip")
        return path

    print(f"  [{name}] generating...")
    client = httpx.Client(base_url=BASE_URL, timeout=600.0)

    body: dict = {
        "model": MODEL,
        "prompt": PIXEL_SPEC + prompt,
        "n": 1,
        "size": size,
        "output_format": "png",
        "response_format": "b64_json",
    }

    if inputs:
        valid = [p for p in inputs if p.exists()]
        if valid:
            body["image"] = base64.b64encode(valid[0].read_bytes()).decode()

    resp = client.post(
        "/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json=body,
    )

    if resp.status_code != 200:
        print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
        return path

    img_bytes = base64.b64decode(resp.json()["data"][0]["b64_json"])
    path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")
    return path


def main():
    print("=" * 60)
    print("V6 PIPELINE — Dependency tree, 32px strict")
    print("=" * 60)

    # ═══════════════════════════════════════════
    # LEVEL 0: Style Reference
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 0: Style Reference ---")
    ref = gen("_reference.png", (
        "A complete room scene in Stardew Valley style. Top-down 3/4 view. "
        "The room is a trader's cozy office, 20 tiles wide × 20 tiles tall (640×640 pixels). "
        "WALLS: dark purple brick (#3d2850) on top and left/right edges, 1 tile thick. "
        "FLOOR: honey wood planks (#c8956c) with darker (#8b5e3c) gaps, horizontal grain. "
        "FURNITURE (all in top-down 3/4 view, same perspective as floor): "
        "- Top-right corner: L-shaped desk (3×2 tiles) with 2 monitors showing green/red charts "
        "- Desk area: purple office chair (1×1 tile) "
        "- Top-left: whiteboard on easel (2×2 tiles) with sticky notes "
        "- Left wall: coffee machine on small table (1×2 tiles) "
        "- Left wall below: server rack (1×2 tiles) with green LEDs "
        "- Bottom-left: purple 2-seat sofa (2×1.5 tiles) with cream pillow "
        "- Bottom wall: low bookshelf (2×1 tiles) with colored spines "
        "- Center: teal oval rug (4×3 tiles) on floor "
        "- Right wall: monstera plant in pot (1×1.5 tiles) "
        "- Right wall: window (2×2 tiles) showing night city skyline "
        "- Scattered: floor lamp, filing cabinet, water cooler "
        "- Walls: clock (1×1) and framed chart poster (1×1) "
        "NO characters/people in scene. Room feels lived-in and spacious. "
        "Every object clearly readable at 32px tile scale. Warm ambient lighting."
    ), "1024x1024")
    time.sleep(2)

    # ═══════════════════════════════════════════
    # LEVEL 1a: Tiles (depend on reference)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 1a: Tiles ---")
    gen("tile_floor.png", (
        "A single seamless 32x32 pixel floor tile. Warm honey wood planks (#c8956c) "
        "with darker (#8b5e3c) plank separation lines. Horizontal grain. "
        "MUST tile seamlessly when repeated. Fill ENTIRE 32x32 area, no transparency. "
        "Output exactly 32x32 pixels."
    ), "1024x1024", inputs=[ref])
    time.sleep(1)

    gen("tile_wall.png", (
        "A single seamless 32x32 pixel wall tile. Dark purple-gray brick (#3d2850) "
        "with slightly lighter (#4a3060) mortar lines between bricks. "
        "MUST tile seamlessly. Fill ENTIRE 32x32 area, no transparency. "
        "Output exactly 32x32 pixels."
    ), "1024x1024", inputs=[ref])
    time.sleep(1)

    # ═══════════════════════════════════════════
    # LEVEL 1b: Character Base (depend on reference)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 1b: Character Base ---")
    char_base = gen("character_base.png", (
        CHAR_LOCK +
        "POSE: standing, facing viewer (front view), perfectly symmetrical. "
        "Arms at sides, feet together, centered in frame. "
        "OUTPUT: single character sprite on transparent background. "
        "The sprite occupies exactly 32×48 pixels in the center of the canvas. "
        "This is the MASTER REFERENCE for all other character sprites."
    ), "1024x1024", inputs=[ref])
    time.sleep(2)

    # ═══════════════════════════════════════════
    # LEVEL 1c: Furniture (depend on reference)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 1c: Furniture ---")

    furniture = {
        "furniture_desk.png": (
            "A single L-shaped office desk seen from top-down 3/4 view (NOT isometric, NOT side view). "
            "EXACTLY 96×64 pixels (3 tiles wide, 2 tiles tall). Transparent background. "
            "Desk surface: warm honey wood (#c8956c). Desk sides/drawers: darker wood (#8b5e3c). "
            "Top surface visible (we look down at it). Front face of desk visible (we see the drawers). "
            "On desk surface: 2 flat monitors (large one shows green/red candlestick chart, "
            "small one shows cyan code), dark keyboard, small mouse. "
            "Same perspective as Stardew Valley furniture. 1px black outline around entire object."
        ),
        "furniture_chair.png": (
            "A single office chair. EXACTLY 32x32 pixels (1 tile). "
            "Transparent background. Dark purple (#4a2860) seat, black base with wheels. "
            "Seen from above showing seat top. Content fills 32x32."
        ),
        "furniture_coffee.png": (
            "A single coffee station. EXACTLY 32x64 pixels (1 tile wide, 2 tiles tall). "
            "Transparent background. Small wood table with black espresso machine on top, "
            "white mug, sugar jar. Content fills 32x64."
        ),
        "furniture_sofa.png": (
            "A single 2-seater couch. EXACTLY 64x48 pixels (2 tiles wide, 1.5 tiles tall). "
            "Transparent background. Dark purple (#6b3a7d) upholstery, one cream pillow. "
            "Seen from 45° above. Content fills 64x48."
        ),
        "furniture_server.png": (
            "A single server rack. EXACTLY 32x64 pixels (1 tile wide, 2 tiles tall). "
            "Transparent background. Dark metal (#2d1f3d), glass front with green/amber LED dots. "
            "Content fills 32x64."
        ),
        "furniture_bookshelf.png": (
            "A single low bookshelf. EXACTLY 64x32 pixels (2 tiles wide, 1 tile tall). "
            "Transparent background. Honey wood, two shelves with colorful book spines. "
            "Small globe on top. Content fills 64x32."
        ),
        "furniture_whiteboard.png": (
            "A single whiteboard on easel. EXACTLY 64x64 pixels (2x2 tiles). "
            "Transparent background. White board with sticky notes (yellow/pink/blue), "
            "chart sketch, marker tray. Content fills 64x64."
        ),
        "furniture_plant.png": (
            "A single potted monstera plant. EXACTLY 32x48 pixels (1 tile wide, 1.5 tiles tall). "
            "Transparent background. Dark pot, green split leaves. Content fills 32x48."
        ),
        "furniture_lamp.png": (
            "A single floor lamp. EXACTLY 32x64 pixels (1 tile wide, 2 tiles tall). "
            "Transparent background. Thin dark stand, warm amber (#f0c060) lampshade at top. "
            "Content fills 32x64."
        ),
        "furniture_rug.png": (
            "A single oval rug seen from directly above. EXACTLY 128x96 pixels (4x3 tiles). "
            "Transparent background. Dark teal (#3d8b8b) with lighter border. Flat on floor. "
            "Content fills 128x96."
        ),
        "furniture_filing.png": (
            "A single filing cabinet. EXACTLY 32x64 pixels (1x2 tiles). "
            "Transparent background. Dark gray metal, 3 drawers with handles. "
            "Content fills 32x64."
        ),
        "furniture_water.png": (
            "A single water cooler. EXACTLY 32x64 pixels (1x2 tiles). "
            "Transparent background. White body, blue water bottle on top. "
            "Content fills 32x64."
        ),
        "furniture_clock.png": (
            "A single round wall clock. EXACTLY 32x32 pixels (1 tile). "
            "Transparent background. White face, dark frame, simple hands. "
            "Content fills ~24x24 centered in 32x32."
        ),
        "furniture_poster.png": (
            "A single framed poster. EXACTLY 32x32 pixels (1 tile). "
            "Transparent background. Dark frame, bullish candlestick chart inside. "
            "Content fills ~28x28 centered in 32x32."
        ),
    }

    furn_paths = {}
    for name, prompt in furniture.items():
        furn_paths[name] = gen(name, prompt, inputs=[ref])
        time.sleep(1)

    # ═══════════════════════════════════════════
    # LEVEL 2a: Character Walk (depends on character_base)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 2a: Character Walk ---")
    char_walk = gen("character_walk.png", (
        CHAR_LOCK +
        "TASK: Create a walk cycle spritesheet for this EXACT character. "
        "LAYOUT: 4 columns × 4 rows grid. Each cell = 32×48 pixels. Total = 128×192 pixels. "
        "Transparent background. "
        "Row 1 (top): walking DOWN (facing viewer). 4 frames: stand, left-leg-forward, stand, right-leg-forward. "
        "Row 2: walking UP (back to viewer). Same 4-frame cycle, showing back of head/hoodie. "
        "Row 3: walking LEFT (side view). 4 frames of walking left. "
        "Row 4 (bottom): walking RIGHT (side view). Mirror of row 3. "
        "CONSISTENCY RULES: "
        "- Head shape, size, hair, and colors are IDENTICAL in every frame. "
        "- Only legs move (2-3px stride). Arms swing 1-2px. "
        "- Hoodie color #4a2860/#6b3a7d unchanged. Pants #2d2d3d unchanged. "
        "- Each frame has the same 1px black outline. "
        "- Character is vertically centered, feet touch bottom edge of each cell."
    ), "1024x1024", inputs=[char_base])
    time.sleep(2)

    # ═══════════════════════════════════════════
    # LEVEL 2b: Interactions (depend on character_base + furniture)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 2b: Interaction Animations ---")

    CHAR_REF = CHAR_LOCK

    interactions = {
        "interact_sit_type.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character sitting (seen from behind), typing on keyboard. "
            "Hands alternate positions. Only character, NO furniture drawn."
        ),
        "interact_sit_think.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character sitting (behind view), one hand on chin, thinking. "
            "Subtle head tilt between frames. Only character, NO furniture."
        ),
        "interact_coffee.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character standing (side view facing right), holding white mug, sipping coffee. "
            "Frames: hold → lift → sip → lower. Only character with mug."
        ),
        "interact_sofa.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character lying down (side view), relaxed/sleeping pose. "
            "Gentle breathing animation. Only character, NO sofa drawn."
        ),
        "interact_whiteboard.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character standing (back view), arm raised writing on whiteboard. "
            "Arm moves in writing motion. Only character, NO whiteboard drawn."
        ),
        "interact_read.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character standing (front view), holding open book, reading. "
            "Slight head nod, page turn. Only character with book."
        ),
        "interact_server.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character standing (back view), reaching toward server panel. "
            "Tapping/checking motion. Only character, NO server drawn."
        ),
        "interact_celebrate.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character (front view) celebrating — jumping with arms raised. "
            "Frames: crouch → jump up (arms high) → peak → landing. Energetic."
        ),
        "interact_frustrated.png": (
            f"4-frame animation spritesheet. Each frame 32x48 px. Total: 128x48 px. "
            f"Transparent background. {CHAR_REF}"
            "Character (front view) frustrated — hands on head, slouched. "
            "Frames: head dropping into hands, slight shake."
        ),
    }

    for name, prompt in interactions.items():
        gen(name, prompt, inputs=[char_base])
        time.sleep(1)

    # ═══════════════════════════════════════════
    # LEVEL 2c: Bubbles (depend on reference)
    # ═══════════════════════════════════════════
    print("\n--- LEVEL 2c: Bubbles ---")
    gen("bubbles.png", (
        "6 speech bubble icons in a horizontal row. Each EXACTLY 32x32 pixels. "
        "Total: 192x32 pixels. Transparent background.\n"
        "Left to right:\n"
        "1. White thought cloud bubble\n"
        "2. Green $ dollar sign in circle\n"
        "3. Blue Zzz (sleep)\n"
        "4. Yellow ! exclamation in triangle\n"
        "5. Cyan magnifying glass (analysis)\n"
        "6. Red down-arrow (loss)\n"
        "Bold 1-2px dark outlines. Bright colors. Each exactly 32x32 cell."
    ), "1024x1024", inputs=[ref])

    print(f"\n{'='*60}")
    print("V6 COMPLETE")
    print(f"{'='*60}")
    for f in sorted(OUT.glob("*.png")):
        sz = f.stat().st_size
        print(f"  {f.name}: {sz:,} bytes")


if __name__ == "__main__":
    main()
