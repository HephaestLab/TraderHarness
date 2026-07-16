"""V7 Production Asset Pipeline — Full asset set for TraderHarness pixel pet.

Character animations: Retro Diffusion (frame-consistent)
Scene/furniture: gpt-image-2-all via vectorengine (single-image assets)

Run: .venv/Scripts/python.exe scripts/generate_v7_production.py
"""

import base64
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

# === API Config ===
VE_KEY = "sk-NFPcrFauZQyQyZUacbUohpdbQVldklH2Ao6uackD7kfvjLhP"
VE_URL = "https://api.vectorengine.ai/v1"
VE_MODEL = "gpt-image-2-all"

RD_KEY = "rdpk-297a8c567ff0f145bcbd4fee61319b5b"
RD_URL = "https://api.retrodiffusion.ai/v1/inferences"

# === Output dirs ===
ROOT = Path(__file__).parent.parent / "assets" / "pixel-art" / "v7-production"
CHAR_DIR = ROOT / "character"
TILES_DIR = ROOT / "tiles"
FURNITURE_DIR = ROOT / "furniture"
UI_DIR = ROOT / "ui"

for d in [CHAR_DIR, TILES_DIR, FURNITURE_DIR, UI_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === Style constants ===
ROOM_STYLE = (
    "STYLE: 16-bit pixel art, exactly like Stardew Valley. "
    "PERSPECTIVE: top-down 3/4 view. NOT isometric. "
    "RENDERING: Each pixel is one solid flat color. Hard edges only. "
    "NO anti-aliasing, NO gradients, NO blur. "
    "OUTLINE: 1px black (#1a1a2e) outline on all sprites. "
    "PALETTE: wood #c8956c/#8b5e3c, wall #3d2850/#4a3060, "
    "purple #6b3a7d/#4a2860, teal #3d8b8b, light #f0c060, screen #40d0d0. "
)

CHAR_PROMPT = (
    "chibi male trader with dark purple messy hair, large over-ear headphones with red LED, "
    "dark purple hoodie, dark gray pants, black shoes, pixel art RPG character"
)


def gen_vectorengine(name: str, prompt: str, size: str = "1024x1024",
                     ref_img: Path | None = None, out_dir: Path | None = None) -> Path:
    """Generate via vectorengine (gpt-image-2-all)."""
    out = out_dir or ROOT
    path = out / name
    if path.exists():
        print(f"  [{name}] exists, skip")
        return path

    print(f"  [{name}] generating...")
    client = httpx.Client(base_url=VE_URL, timeout=600.0)
    body = {
        "model": VE_MODEL, "prompt": prompt, "n": 1,
        "size": size, "output_format": "png", "response_format": "b64_json",
    }
    if ref_img and ref_img.exists():
        body["image"] = base64.b64encode(ref_img.read_bytes()).decode()

    resp = client.post("/images/generations",
                       headers={"Authorization": f"Bearer {VE_KEY}"}, json=body)
    if resp.status_code != 200:
        print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
        return path

    img_bytes = base64.b64decode(resp.json()["data"][0]["b64_json"])
    path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")
    return path


def gen_retrodiffusion(name: str, prompt: str, style: str,
                       width: int, height: int,
                       input_img: Path | None = None,
                       out_dir: Path | None = None) -> Path:
    """Generate via Retro Diffusion."""
    out = out_dir or CHAR_DIR
    path = out / name
    if path.exists():
        print(f"  [{name}] exists, skip")
        return path

    print(f"  [{name}] generating (RD: {style})...")

    payload: dict = {
        "prompt": prompt,
        "prompt_style": style,
        "width": width,
        "height": height,
        "num_images": 1,
        "return_spritesheet": True,
    }

    if input_img and input_img.exists():
        img = Image.open(input_img)
        if img.size[0] > 256 or img.size[1] > 256:
            img = img.resize((256, 256), Image.NEAREST)
        img = img.convert("RGBA")
        pixels = list(img.getdata())
        cleaned = [(0, 0, 0, 0) if (p[0] > 200 and p[1] < 80 and p[2] > 200) else p
                   for p in pixels]
        img.putdata(cleaned)
        buf = BytesIO()
        img.save(buf, format="PNG")
        payload["input_image"] = base64.b64encode(buf.getvalue()).decode()

    resp = httpx.post(RD_URL, headers={"X-RD-Token": RD_KEY}, json=payload, timeout=120)

    if resp.status_code != 200:
        print(f"    ERROR {resp.status_code}: {resp.text[:200]}")
        return path

    data = resp.json()
    images = data.get("base64_images", [])
    if images:
        path.write_bytes(base64.b64decode(images[0]))
        print(f"    OK: {path.stat().st_size:,} bytes (bal: {data.get('remaining_balance', '?')})")
    else:
        print(f"    ERROR: no images returned")
    return path


def generate_character():
    """Generate all character animations via Retro Diffusion."""
    print("\n" + "=" * 60)
    print("CHARACTER ANIMATIONS (Retro Diffusion)")
    print("=" * 60)

    anchor = Path("assets/pixel-art/v7/anchors/02-south-anchor.png")
    if not anchor.exists():
        print("  ERROR: Need south anchor first! Run generate_v7_assets.py")
        return

    # 4-angle walking (the main one)
    gen_retrodiffusion(
        "walk-4angle.png", CHAR_PROMPT + ", walking cycle",
        "animation__four_angle_walking", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )
    time.sleep(2)

    # Walking + idle combined
    gen_retrodiffusion(
        "walk-and-idle.png", CHAR_PROMPT + ", walking and idle animation",
        "animation__walking_and_idle", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )
    time.sleep(2)

    # Celebrate/happy interaction
    gen_retrodiffusion(
        "interact-celebrate.png", CHAR_PROMPT + ", jumping celebration, arms raised, happy",
        "animation__small_sprites", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )
    time.sleep(2)

    # Typing at desk
    gen_retrodiffusion(
        "interact-typing.png", CHAR_PROMPT + ", sitting typing on keyboard, back view",
        "animation__small_sprites", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )
    time.sleep(2)

    # Drinking coffee
    gen_retrodiffusion(
        "interact-coffee.png", CHAR_PROMPT + ", drinking from a mug, side view",
        "animation__small_sprites", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )
    time.sleep(2)

    # Frustrated (loss)
    gen_retrodiffusion(
        "interact-frustrated.png", CHAR_PROMPT + ", frustrated head in hands, slouched",
        "animation__small_sprites", 48, 48,
        input_img=anchor, out_dir=CHAR_DIR
    )


def generate_tiles():
    """Generate floor and wall tiles."""
    print("\n" + "=" * 60)
    print("TILES (vectorengine)")
    print("=" * 60)

    gen_vectorengine("tile_floor.png", (
        ROOM_STYLE +
        "A single seamless 32x32 pixel floor tile. Warm honey wood planks (#c8956c) "
        "with darker (#8b5e3c) plank separation lines. Horizontal grain. "
        "MUST tile seamlessly. Fill ENTIRE canvas. No transparency. "
        "Output the tile centered in the image."
    ), out_dir=TILES_DIR)
    time.sleep(1)

    gen_vectorengine("tile_wall.png", (
        ROOM_STYLE +
        "A single seamless 32x32 pixel wall tile. Dark purple-gray brick (#3d2850) "
        "with slightly lighter (#4a3060) mortar lines. "
        "MUST tile seamlessly. Fill ENTIRE canvas. No transparency."
    ), out_dir=TILES_DIR)


def generate_furniture():
    """Generate individual furniture sprites."""
    print("\n" + "=" * 60)
    print("FURNITURE (vectorengine)")
    print("=" * 60)

    furniture_specs = {
        "desk.png": (
            "A single L-shaped office desk, top-down 3/4 view (NOT isometric). "
            "Honey wood (#c8956c) surface, darker (#8b5e3c) drawers/sides. "
            "On surface: 2 monitors (one with green/red candlestick chart, one with cyan code), "
            "dark keyboard, mouse. Transparent background. 1px black outline."
        ),
        "chair.png": (
            "A single office chair seen from top-down 3/4 view. "
            "Dark purple (#4a2860) seat, black base with small wheels. "
            "Transparent background. 1px black outline."
        ),
        "sofa.png": (
            "A single 2-seat couch, top-down 3/4 view. "
            "Dark purple (#6b3a7d) upholstery, one cream pillow. "
            "Transparent background. 1px black outline."
        ),
        "server.png": (
            "A single server rack, top-down 3/4 view. "
            "Dark metal frame, glass front with green and amber LED dots in rows. "
            "Transparent background. 1px black outline."
        ),
        "bookshelf.png": (
            "A single low bookshelf, top-down 3/4 view. "
            "Honey wood frame, two shelves with colorful book spines (red, blue, green, yellow). "
            "Small globe on top. Transparent background. 1px black outline."
        ),
        "coffee_machine.png": (
            "A single coffee station on small table, top-down 3/4 view. "
            "Wood table, black espresso machine, white mug, sugar jar. "
            "Transparent background. 1px black outline."
        ),
        "plant.png": (
            "A single potted monstera plant, top-down 3/4 view. "
            "Dark brown pot, green split leaves. "
            "Transparent background. 1px black outline."
        ),
        "whiteboard.png": (
            "A single whiteboard on easel, top-down 3/4 view. "
            "White board with colorful sticky notes (yellow, pink, blue), "
            "chart sketch, marker tray. Transparent background. 1px black outline."
        ),
        "rug.png": (
            "A single oval rug seen from directly above. "
            "Dark teal (#3d8b8b) with lighter teal border pattern. Flat on floor. "
            "Transparent background."
        ),
        "lamp.png": (
            "A single floor lamp, top-down 3/4 view. "
            "Thin dark stand, warm amber (#f0c060) cone lampshade at top. "
            "Transparent background. 1px black outline."
        ),
        "window.png": (
            "A single window showing night city skyline, top-down 3/4 view. "
            "Dark wood frame, glass panes, city buildings with small lit windows outside. "
            "Transparent background (around the window frame). 1px black outline."
        ),
    }

    for name, prompt in furniture_specs.items():
        gen_vectorengine(name, ROOM_STYLE + prompt, out_dir=FURNITURE_DIR)
        time.sleep(1)


def generate_ui():
    """Generate UI bubble icons."""
    print("\n" + "=" * 60)
    print("UI ELEMENTS (vectorengine)")
    print("=" * 60)

    gen_vectorengine("bubbles.png", (
        ROOM_STYLE +
        "6 speech/thought bubble icons in a horizontal row. Each exactly 32x32 pixels. "
        "Total image: 192x32 pixels. Transparent background. "
        "Left to right: "
        "1. White thought cloud bubble. "
        "2. Green $ dollar sign in circle (profit). "
        "3. Blue Zzz (sleeping). "
        "4. Yellow ! exclamation in triangle (alert). "
        "5. Cyan magnifying glass (analysis). "
        "6. Red down-arrow (loss). "
        "Bold 1-2px dark outlines. Bright solid colors."
    ), out_dir=UI_DIR)


def main():
    print("=" * 60)
    print("V7 PRODUCTION — Full Asset Generation")
    print("=" * 60)
    print(f"  Character: Retro Diffusion (RD)")
    print(f"  Scene/Furniture: gpt-image-2-all (VE)")
    print(f"  Output: {ROOT}")

    generate_character()
    generate_tiles()
    generate_furniture()
    generate_ui()

    print(f"\n{'=' * 60}")
    print("PRODUCTION COMPLETE")
    print(f"{'=' * 60}")
    for d in [CHAR_DIR, TILES_DIR, FURNITURE_DIR, UI_DIR]:
        files = list(d.glob("*.png"))
        print(f"\n  {d.name}/ ({len(files)} files)")
        for f in sorted(files):
            print(f"    {f.name}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
