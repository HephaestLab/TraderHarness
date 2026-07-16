"""Generate pixel-art assets V2: top-down room + walking character.

Run: .venv/Scripts/python.exe scripts/generate_pixel_assets_v2.py
"""

import base64
import time
from pathlib import Path

import httpx

API_KEY = "sk-52f492dba72b382a0661523b7ed7c83b7787bce0931408cf47ff497492b059eb"
BASE_URL = "https://vip.auto-code.net"
MODEL = "gpt-image-1"
OUTPUT_DIR = Path(__file__).parent.parent / "assets" / "pixel-art"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = {
    "scene_room.png": {
        "prompt": (
            "Top-down pixel art room interior, 16-bit retro game style, seen from a slightly "
            "elevated angle (about 30 degrees from above, like Stardew Valley or the game Unpacking).\n\n"
            "A cozy trader's private office room. Warm, lived-in feeling.\n\n"
            "Layout from top-left to bottom-right:\n"
            "- TOP WALL: Dark purple-brown brick wall. A large window on the right showing "
            "city night skyline with tiny orange/blue lights. A framed green candlestick chart poster "
            "on the wall center. Small decorative shelf with a few items on the left.\n"
            "- TOP-LEFT corner: A whiteboard mounted on the wall, with colorful sticky notes "
            "(yellow, pink, blue) and hand-drawn chart diagrams.\n"
            "- TOP-RIGHT corner: A tall black server rack cabinet with rows of blinking LED dots "
            "(green and red), small warning sign sticker, cable management visible.\n"
            "- CENTER-LEFT: A large L-shaped wooden desk. On the desk: two monitors (one large landscape "
            "showing green candlestick chart, one smaller portrait showing blue code), a mechanical keyboard, "
            "mouse, and a warm yellow desk lamp. An office chair (dark purple) in front.\n"
            "- CENTER: Open floor area with a round teal/dark-green area rug.\n"
            "- CENTER-RIGHT: A small wooden coffee station table with a coffee machine, white mug, "
            "and a small plant on top.\n"
            "- BOTTOM-LEFT: Large potted monstera plant with big green leaves.\n"
            "- BOTTOM-RIGHT: A comfortable dark purple couch/sofa with a light pillow, facing left.\n"
            "- BOTTOM-CENTER: A low bookshelf with colorful book spines (red, blue, yellow, green).\n\n"
            "Floor: warm honey-colored wooden planks, clearly visible between furniture.\n"
            "Walls: upper half is dark purple-gray brick, lower half has light wood wainscoting.\n\n"
            "Lighting: warm yellow from desk lamp, cool blue/green from monitor screens, warm amber "
            "from the window (city glow). Small purple-pink LED strip along the bottom of the server rack.\n\n"
            "IMPORTANT: There must be clear WALKABLE PATHS between all furniture pieces. A small character "
            "needs to be able to walk from the desk to the coffee table, to the sofa, to the server rack, etc. "
            "Leave at least 32 pixels of open floor between furniture items.\n\n"
            "NO people or characters in the scene. Just the empty furnished room.\n\n"
            "Style: Clean pixel art, 16x16 base grid scaled up. Crisp pixel edges, NO anti-aliasing, "
            "NO dithering on outlines. Similar to Stardew Valley indoor scenes or Undertale houses. "
            "Warm and cozy atmosphere."
        ),
        "size": "1536x1024",
    },
    "trader_char.png": {
        "prompt": (
            "Pixel art character spritesheet for a top-down 2D game. 16-bit retro style.\n\n"
            "Character: A cute chibi/SD-proportion young male trader. Big round head relative to body "
            "(roughly 1:1.2 head-to-body ratio). Short messy dark hair. Wearing a purple hoodie "
            "(dark purple #533483 body, lighter purple #8854d0 on chest/pocket area), dark gray pants, "
            "and small black shoes. Has chunky over-ear headphones resting around his neck (dark gray "
            "with a small red LED dot). Round friendly face with simple dot eyes and a tiny smile.\n\n"
            "The character sprite should be about 24 pixels wide and 32 pixels tall within each cell.\n\n"
            "SPRITESHEET LAYOUT on solid magenta (#FF00FF) background:\n"
            "Total image: 256x224 pixels (8 columns x 7 rows, each cell 32x32 pixels).\n\n"
            "Row 0 (top): Walking DOWN (facing viewer) 4 frames walk cycle | "
            "Walking UP (back to viewer) 4 frames walk cycle\n"
            "Row 1: Walking LEFT 4 frames | Walking RIGHT 4 frames\n"
            "Row 2: Sitting at desk TYPING (side view, hands on keyboard) 4 frames | "
            "Sitting THINKING (hand on chin, slight head tilt) 4 frames\n"
            "Row 3: Standing holding COFFEE MUG (side view, sipping) 4 frames | "
            "Standing at WHITEBOARD writing (back view, arm raised) 4 frames\n"
            "Row 4: LYING on sofa (side view, relaxed) 4 frames | "
            "Standing READING a book (front-ish view) 4 frames\n"
            "Row 5: CELEBRATING (jumping, arms up, happy) 4 frames | "
            "FRUSTRATED (head in hands, slouched) 4 frames\n"
            "Row 6: Standing IDLE (gentle breathing) 2 frames | "
            "Looking at WINDOW (back view) 2 frames | "
            "Checking SERVER (side view, touching panel) 4 frames\n\n"
            "CRITICAL REQUIREMENTS:\n"
            "- Character must look IDENTICAL across all frames (same proportions, same colors)\n"
            "- Walk cycle frames must show clear leg movement progression\n"
            "- Each 32x32 cell must have the character CENTERED with some padding\n"
            "- Clean pixel art, NO anti-aliasing, NO blurring between pixels\n"
            "- The character should be CUTE and READABLE even at small sizes\n"
            "- Style similar to Stardew Valley villager sprites or Undertale overworld sprites"
        ),
        "size": "1024x1024",
    },
    "ui_bubbles.png": {
        "prompt": (
            "Pixel art UI elements spritesheet on solid magenta (#FF00FF) background.\n"
            "16-bit retro game style. Clean, bold, easily readable.\n\n"
            "Total image: 256x128 pixels. Grid of 32x32 pixel cells (8 columns x 4 rows).\n\n"
            "Row 0 - Speech/Status Bubbles (each is a small bubble icon, about 20x20 pixels centered "
            "in the 32x32 cell):\n"
            "1. White speech bubble (pointed tail at bottom)\n"
            "2. White thought cloud bubble (bumpy edges)\n"
            "3. Yellow exclamation bubble (! inside)\n"
            "4. Blue music note bubble (♪ inside)\n"
            "5. Light blue Zzz sleep bubble\n"
            "6. Pink heart bubble\n"
            "7. Green dollar sign bubble ($)\n"
            "8. Red down-arrow bubble (loss indicator)\n\n"
            "Row 1 - Status Icons:\n"
            "1. Green up arrow (profit)\n"
            "2. Red down arrow (loss)\n"
            "3-4. Gold coin spinning (2 key frames)\n"
            "5-6. White coffee cup with rising steam (2 frames)\n"
            "7. Lightning bolt (yellow, for code execution)\n"
            "8. Magnifying glass (for analysis)\n\n"
            "Row 2 - Emotion Effects:\n"
            "1-2. Yellow star sparkles (2 frames)\n"
            "3-4. Blue sweat drops (2 frames)\n"
            "5-6. Red anger cross marks (2 frames)\n"
            "7-8. White question marks floating (2 frames)\n\n"
            "Row 3 - Interaction Markers:\n"
            "1. White glowing circle (interaction spot)\n"
            "2. Small down-pointing arrow (destination marker)\n"
            "3. Green checkmark\n"
            "4. Red X mark\n"
            "5-6. Hourglass (2 frames, sand flowing)\n"
            "7. Small clock\n"
            "8. Gear/settings icon\n\n"
            "Style: Each icon has a 1-2px dark outline. Bright, saturated colors. "
            "Must be clearly distinguishable and readable at 32x32 pixel size. "
            "No anti-aliasing. Bold pixel art."
        ),
        "size": "1024x1024",
    },
}


def generate_image(name: str, config: dict) -> None:
    output_path = OUTPUT_DIR / name
    print(f"\n{'='*60}")
    print(f"Generating: {name}")
    print(f"Size: {config['size']}")
    print(f"{'='*60}")

    client = httpx.Client(base_url=BASE_URL, timeout=300.0)
    resp = client.post(
        "/v1/images/generations",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={
            "model": MODEL,
            "prompt": config["prompt"],
            "n": 1,
            "size": config["size"],
            "response_format": "b64_json",
        },
    )

    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        return

    data = resp.json()
    b64_data = data["data"][0]["b64_json"]
    img_bytes = base64.b64decode(b64_data)
    output_path.write_bytes(img_bytes)
    print(f"Saved: {output_path} ({len(img_bytes):,} bytes)")


def main() -> None:
    for name, config in PROMPTS.items():
        generate_image(name, config)
        time.sleep(2)

    print(f"\n{'='*60}")
    print("All V2 assets generated!")
    for f in sorted(OUTPUT_DIR.glob("*.png")):
        print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
