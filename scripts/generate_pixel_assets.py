"""Generate pixel-art assets for the trader scene using GPT-Image-2 API.

Run: .venv/Scripts/python.exe scripts/generate_pixel_assets.py
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
    "scene_bg.png": {
        "prompt": (
            "Pixel art, 16-bit retro game style, top-down 3/4 perspective view of a cozy "
            "trading office room at night. The view is from slightly above and behind, looking "
            "toward the monitors.\n\n"
            "Scene layout:\n"
            "- Dark purple-gray walls (hex #2d2040) with subtle brick/panel texture\n"
            "- A wide wooden desk with dual monitors:\n"
            "  - One large landscape monitor showing green candlestick chart with red/green bars\n"
            "  - One smaller portrait monitor showing blue scrolling code/data\n"
            "- An ergonomic office chair (dark purple/black) facing the monitors. "
            "The chair is EMPTY — no person sitting in it\n"
            "- Desktop items: white steaming coffee mug, small stack of papers, tiny green potted succulent\n"
            "- Purple-pink LED strip light along desk edge, casting soft neon glow on the floor\n"
            "- Wall decorations: small analog clock (white face), framed mini candlestick chart poster, "
            "3-4 colorful sticky notes (yellow, pink, cyan)\n"
            "- Dark hardwood floor (hex #3d2b56)\n"
            "- Small window on the right wall showing a dark city night skyline with tiny glowing lights\n"
            "- Warm desk lamp on the left casting soft yellow light\n"
            "- Keyboard and mouse on the desk in front of the chair\n\n"
            "Color palette: warm purples (#2d2040, #3d2b56, #4a3660), pink accents (#e94560), "
            "cyan monitor glow (#00d2d3), yellow lamp light (#f9ca24), green data (#10b981).\n\n"
            "Atmosphere: cozy late-night work session, mix of warm lamp light and cool monitor glow.\n"
            "Style: clean pixel art like Stardew Valley or Celeste, no anti-aliasing, crisp pixel edges, "
            "consistent 16-pixel grid. The image should work as a background layer with a character "
            "overlaid on the chair area later."
        ),
        "size": "1536x1024",
    },
    "trader_sprite.png": {
        "prompt": (
            "Pixel art character spritesheet on a solid magenta (#FF00FF) background for chroma keying.\n\n"
            "Character: A young trader seen from 3/4 back view (facing away from viewer, toward monitors). "
            "Wearing a purple hoodie (hex #533483 body, #8854d0 highlights), with large over-ear headphones "
            "that have a small glowing red antenna light. Short dark hair visible. Sitting in a dark "
            "office chair.\n\n"
            "Spritesheet layout: 4 columns wide, 7 rows tall. Each cell is exactly 64x64 pixels. "
            "Total image: 256 pixels wide x 448 pixels tall.\n\n"
            "Rows (top to bottom), each row has 4 animation frames showing progression:\n"
            "Row 1 - IDLE: Slight breathing, hand on mouse, minimal movement between frames\n"
            "Row 2 - ANALYZING: Head tilted right, hand on chin (thinking pose), looking at screen\n"
            "Row 3 - TRADING: Leaning forward, both hands moving on keyboard, typing fast\n"
            "Row 4 - EXCITED: Arms raised up in celebration, slight chair bounce, fist pump\n"
            "Row 5 - STRESSED: Both hands on head, leaning back, frustrated body language\n"
            "Row 6 - WAITING: Body turned slightly right, holding a coffee mug, relaxed\n"
            "Row 7 - SLEEPING: Head face-down on desk, small Zzz text bubbles above\n\n"
            "Colors: skin (#feca57, #f8b739 shadow), hoodie (#533483 base, #8854d0 light), "
            "chair (#2d2040), headphones (#2d2040 with #e94560 LED dot), "
            "coffee mug (white with purple stripe).\n\n"
            "Style: clean 16-bit pixel art, NO anti-aliasing, consistent perspective and scale across "
            "ALL 28 frames. Each frame within a row should show clear animation progression. "
            "Character should be roughly 40-48 pixels tall within the 64px cell, centered."
        ),
        "size": "1024x1024",
    },
    "ui_elements.png": {
        "prompt": (
            "Pixel art UI elements spritesheet on a solid magenta (#FF00FF) background.\n\n"
            "Image size: 256x256 pixels, divided into an 8x8 grid where each cell is 32x32 pixels.\n\n"
            "Contents (left to right, top to bottom):\n"
            "Row 1: Coffee steam animation — 4 frames showing wispy white-gray steam rising, "
            "then 4 blank cells\n"
            "Row 2: Sleep Zzz animation — 4 frames showing blue 'Z' letters floating up "
            "(small to large), then 4 blank cells\n"
            "Row 3: Emotion indicators — green up arrow, red down arrow, yellow exclamation mark (!), "
            "blue question mark (?), green checkmark, red X, yellow star, pink heart\n"
            "Row 4: Chart elements — single green candlestick (bullish), single red candlestick (bearish), "
            "small green line going up, small red line going down, gold coin, silver coin, "
            "dollar sign, percent sign\n"
            "Row 5-8: Repeat patterns or blank cells\n\n"
            "Style: clean 16-bit pixel art, bright saturated colors, each element cleanly contained "
            "within its 32x32 cell. No anti-aliasing. Bold outlines (1-2px dark)."
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
    print(f"Saved: {output_path} ({len(img_bytes)} bytes)")


def main() -> None:
    for name, config in PROMPTS.items():
        generate_image(name, config)
        time.sleep(2)

    print(f"\n{'='*60}")
    print("All assets generated!")
    print(f"Output directory: {OUTPUT_DIR}")
    for f in OUTPUT_DIR.iterdir():
        if f.suffix == ".png":
            print(f"  {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
