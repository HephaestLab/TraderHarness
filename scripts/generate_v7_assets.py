"""V7 Asset Pipeline — Anchor-chain method (chongdashu methodology).

Pipeline:
  Step 1: Box Art — high-res concept portrait (establishes identity)
  Step 2: South Anchor — grid-constrained game sprite (THE canonical reference)
  Step 3: Neutral Anchor — strip effects, clean idle pose
  Step 4: Directional Anchors — West, North (East = flip West)
  Step 5: Walk Cycle — image-to-video or animation model (TODO: needs fal.ai/RD key)
  Step 6: Attack Spritesheet — 5x2 grid, 10 frames
  Step 7: Idle Spritesheet — 5x2 grid, 10 frames (subtle)
  Step 8: Normalization — bg removal, foot anchoring, height correction

Key insight: "Image gen = 20% of the work. The other 80% is the pipeline."
Every step feeds its output as input to the next — consistency through chaining.

Model: gpt-image-2-all via vectorengine.ai
Run: .venv/Scripts/python.exe scripts/generate_v7_assets.py

Reference: https://github.com/chongdashu/ai-game-spritesheets
"""

import base64
import json
import time
from pathlib import Path

import httpx

API_KEY = "sk-NFPcrFauZQyQyZUacbUohpdbQVldklH2Ao6uackD7kfvjLhP"
BASE_URL = "https://api.vectorengine.ai/v1"
MODEL = "gpt-image-2-all"

ROOT = Path(__file__).parent.parent / "assets" / "pixel-art" / "v7"
REFS = ROOT / "references"
ANCHORS = ROOT / "anchors"
ANIMS = ROOT / "animations"

for d in [ROOT, REFS, ANCHORS, ANIMS]:
    d.mkdir(parents=True, exist_ok=True)

# Character definition — single source of truth
CHARACTER = {
    "name": "Trader",
    "archetype": "chibi male pixel-art trader with headphones",
    "silhouette": (
        "Large round head (40% of total height), short stubby body. "
        "Oversized head reads clearly at 32px scale."
    ),
    "costume": (
        "Dark purple hoodie (#4a2860 body, #6b3a7d hood/sleeves). "
        "Dark gray pants (#2d2d3d). Black shoes (#1a1a2e). "
        "Headphones with thin dark band, tiny red LED dot on right ear."
    ),
    "props": "No held items in idle pose.",
    "palette": (
        "skin #f0c890, hair #2d1f3d (messy dark purple, covers forehead), "
        "hoodie-dark #4a2860, hoodie-light #6b3a7d, pants #2d2d3d, "
        "shoes #1a1a2e, headphone-led #ff3030"
    ),
}

# Frame specs
LOGICAL_SIZE = "32x48"  # in-game sprite size
OUTPUT_SIZE = "1024x1024"  # generation size (each pixel = block of pixels)
CHROMA = "#FF00FF"  # magenta chroma key background


def gen(name: str, prompt: str, size: str = "1024x1024",
        inputs: list[Path] | None = None, subdir: Path | None = None) -> Path:
    """Generate one image. Inputs are reference images passed for consistency."""
    out_dir = subdir or ROOT
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name

    if path.exists():
        print(f"  [{name}] exists, skip")
        return path

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
        print(f"    ERROR {resp.status_code}: {resp.text[:300]}")
        return path

    img_bytes = base64.b64decode(resp.json()["data"][0]["b64_json"])
    path.write_bytes(img_bytes)
    print(f"    OK: {len(img_bytes):,} bytes")
    return path


def step1_box_art() -> Path:
    """High-res concept portrait — establishes visual identity."""
    print("\n" + "=" * 60)
    print("STEP 1: Box Art (concept portrait)")
    print("=" * 60)

    prompt = (
        f"A high-quality character portrait illustration of {CHARACTER['name']}, "
        f"a {CHARACTER['archetype']}. "
        f"Appearance: {CHARACTER['silhouette']} "
        f"Costume: {CHARACTER['costume']} "
        f"Setting: dramatic portrait against a dark background with subtle "
        f"trading chart lines (green/red) glowing behind. "
        f"Style: polished pixel art illustration, vibrant colors, "
        f"clear readable silhouette, warm lighting from above-left. "
        f"Palette: {CHARACTER['palette']}. "
        f"This is a character concept/box art — detailed, expressive, iconic."
    )
    return gen("01-box-art.png", prompt, OUTPUT_SIZE, subdir=ROOT)


def step2_south_anchor(box_art: Path) -> Path:
    """THE most important image — grid-constrained south-facing game sprite."""
    print("\n" + "=" * 60)
    print("STEP 2: South Anchor (canonical game sprite)")
    print("=" * 60)

    grid_ref = REFS / "pixel-grid-1024.png"

    prompt = (
        f"Intended use: a single south-facing idle sprite frame for a top-down 2D action game. "
        f"Final artwork should behave like one logical {LOGICAL_SIZE} in-game frame, "
        f"delivered at {OUTPUT_SIZE} so each sprite pixel reads as a clean block.\n\n"
        f"Image 1 role: pixel-grid anchor. Use it ONLY to enforce chunky pixel-art "
        f"block discipline and a centered single-frame composition. Do not copy its content.\n\n"
        f"Subject:\n"
        f"- {CHARACTER['name']}, {CHARACTER['archetype']}, facing SOUTH directly toward "
        f"the camera in 3/4 top-down game perspective.\n"
        f"- This is the canonical idle frame.\n"
        f"- {CHARACTER['silhouette']}\n"
        f"- {CHARACTER['costume']}\n"
        f"- {CHARACTER['props']}\n"
        f"- Calm readable idle expression/pose.\n\n"
        f"Frame rules:\n"
        f"- One character only, centered.\n"
        f"- Full body visible.\n"
        f"- Visible body fits within the intended logical sprite box.\n"
        f"- Anchor/foot plant at bottom-center.\n"
        f"- Preserve idle readability, not an attack pose.\n\n"
        f"Style:\n"
        f"- polished SNES-era / high-resolution pixelated game sprite\n"
        f"- chunky readable silhouette\n"
        f"- crisp edges, NO anti-aliasing halos\n"
        f"- limited surface shading plus small highlight pixels\n"
        f"- consistent top-left light source\n"
        f"- Palette: {CHARACTER['palette']}\n\n"
        f"Background:\n"
        f"- solid removable chroma color {CHROMA} outside the sprite silhouette\n"
        f"- no scenery, props, borders, UI, text, logo, or watermark\n\n"
        f"Avoid:\n"
        f"- photorealism, painterly blending\n"
        f"- anti-aliased halos\n"
        f"- extra characters\n"
        f"- complex background"
    )
    return gen("02-south-anchor.png", prompt, OUTPUT_SIZE, inputs=[grid_ref], subdir=ANCHORS)


def step3_neutral_anchor(south_anchor: Path) -> Path:
    """Strip all effects — clean neutral standing pose for animation base."""
    print("\n" + "=" * 60)
    print("STEP 3: Neutral Anchor (effects stripped)")
    print("=" * 60)

    prompt = (
        f"Take the character from Image 1 and create a perfectly neutral version:\n\n"
        f"KEEP EXACTLY:\n"
        f"- Same character identity, proportions, silhouette, palette, outfit\n"
        f"- Same south-facing direction and 3/4 top-down perspective\n"
        f"- Same pixel-art style, same resolution, same scale\n"
        f"- Same {CHROMA} chroma background\n\n"
        f"REMOVE/NEUTRALIZE:\n"
        f"- Any baked-in effects, particles, glows, or magic\n"
        f"- Any action pose — return to calm neutral standing\n"
        f"- Arms relaxed at sides, feet together, weight evenly distributed\n"
        f"- No dynamic cloth movement or wind effects\n\n"
        f"This neutral pose is the ANIMATION BASE. Every walk frame, attack frame, "
        f"and idle frame will be derived from this exact pose. "
        f"It must be the cleanest, most stable version of the character.\n\n"
        f"Output: single character, centered, full body, foot plant at bottom-center, "
        f"solid {CHROMA} background, no scenery/UI/text."
    )
    return gen("03-neutral-south.png", prompt, OUTPUT_SIZE, inputs=[south_anchor], subdir=ANCHORS)


def step4_directional_anchors(neutral: Path) -> Path:
    """Generate West and North anchors. East = flip of West."""
    print("\n" + "=" * 60)
    print("STEP 4: Directional Anchors (West, North)")
    print("=" * 60)

    # West anchor
    west_prompt = (
        f"Take the character from Image 1 and rotate them to face WEST (left side of frame).\n\n"
        f"KEEP EXACTLY:\n"
        f"- Same character identity, proportions, outfit, palette, pixel style\n"
        f"- Same scale, same foot baseline position\n"
        f"- Same neutral standing pose (arms at sides, relaxed)\n"
        f"- Same {CHROMA} chroma background\n"
        f"- Same resolution and sprite-block discipline\n\n"
        f"CHANGE ONLY:\n"
        f"- Character now faces LEFT (west direction)\n"
        f"- We see the character's right side profile\n"
        f"- Head turned left, body oriented left\n\n"
        f"The character is IDENTICAL to Image 1 in every way except facing direction. "
        f"Do NOT change costume, proportions, colors, or add/remove any details.\n\n"
        f"Output: single character, centered, full body, solid {CHROMA} background."
    )
    west = gen("04-anchor-west.png", west_prompt, OUTPUT_SIZE, inputs=[neutral], subdir=ANCHORS)
    time.sleep(2)

    # North anchor
    north_prompt = (
        f"Take the character from Image 1 and rotate them to face NORTH (away from camera).\n\n"
        f"KEEP EXACTLY:\n"
        f"- Same character identity, proportions, outfit, palette, pixel style\n"
        f"- Same scale, same foot baseline position\n"
        f"- Same neutral standing pose (arms at sides, relaxed)\n"
        f"- Same {CHROMA} chroma background\n"
        f"- Same resolution and sprite-block discipline\n\n"
        f"CHANGE ONLY:\n"
        f"- Character now faces AWAY from camera (we see their back)\n"
        f"- Back of head, back of hoodie visible\n"
        f"- Headphone band visible across back of head\n\n"
        f"The character is IDENTICAL to Image 1 in every way except facing direction. "
        f"Do NOT change costume, proportions, colors, or add/remove any details.\n\n"
        f"Output: single character, centered, full body, solid {CHROMA} background."
    )
    north = gen("04-anchor-north.png", north_prompt, OUTPUT_SIZE, inputs=[neutral], subdir=ANCHORS)

    return west


def step5_walk_placeholder():
    """Walk cycle — requires image-to-video (SeedDance 2.0 / fal.ai) or Retro Diffusion.

    This step is a PLACEHOLDER. To complete it you need either:
    - fal.ai API key (SeedDance 2.0 image-to-video)
    - Retro Diffusion API key (animation__four_angle_walking)

    The process:
    1. Pass each directional anchor to i2v model
    2. Generate ~4s video of character walking in place
    3. Pick 8-12 frames for one clean loop
    4. Export as spritesheet
    """
    print("\n" + "=" * 60)
    print("STEP 5: Walk Cycle (PLACEHOLDER — needs fal.ai or RD key)")
    print("=" * 60)
    print("  This step requires image-to-video generation.")
    print("  Options:")
    print("    A) fal.ai SeedDance 2.0 — image-to-video, pick frames")
    print("    B) Retro Diffusion animation__four_angle_walking ($0.07/gen)")
    print("  Skipping for now...")


def step6_idle_spritesheet(neutral: Path) -> Path:
    """Generate subtle idle animation — 5x2 grid, 10 frames."""
    print("\n" + "=" * 60)
    print("STEP 6: Idle Spritesheet (5x2, 10 frames)")
    print("=" * 60)

    guide = REFS / "sheet-guide-5x2.png"

    prompt = (
        f"Create a 10-frame 5x2 spritesheet for a top-down 2D game character IDLE animation.\n\n"
        f"Input images:\n"
        f"Image 1 is the identity anchor for {CHARACTER['name']}. Preserve the EXACT character "
        f"identity, outfit, proportions, palette, and south-facing direction.\n\n"
        f"Primary request:\n"
        f"Generate {CHARACTER['name']} performing a subtle south-facing IDLE breathing loop. "
        f"The character faces SOUTH (toward camera) for every frame. "
        f"Movement is VERY subtle — gentle breathing, tiny sway.\n\n"
        f"Canvas and layout:\n"
        f"- 1280x512 PNG spritesheet\n"
        f"- 5 columns by 2 rows\n"
        f"- ten equal 256x256 cells\n"
        f"- frame order: left to right across top row, then left to right across bottom row\n"
        f"- character fully visible in each cell, including both feet\n"
        f"- consistent character scale, camera, and ground baseline across all frames\n"
        f"- solid {CHROMA} chroma background\n\n"
        f"Frame sequence:\n"
        f"Frame 1: neutral stance, feet planted.\n"
        f"Frame 2: very slight inhale, shoulders rise 1-2px.\n"
        f"Frame 3: peak inhale.\n"
        f"Frame 4: exhale begins, shoulders lower.\n"
        f"Frame 5: return to neutral.\n"
        f"Frame 6: slight weight shift to left foot (1px).\n"
        f"Frame 7: neutral.\n"
        f"Frame 8: slight weight shift to right foot (1px).\n"
        f"Frame 9: settling back.\n"
        f"Frame 10: return to frame 1 stance (seamless loop).\n\n"
        f"Style:\n"
        f"- high-resolution pixel-art-inspired game sprite\n"
        f"- crisp edges, consistent lighting and palette: {CHARACTER['palette']}\n"
        f"- readable silhouette\n\n"
        f"Constraints:\n"
        f"- NO direction change between frames\n"
        f"- NO camera angle change\n"
        f"- NO extra characters, scenery, UI, labels, text, watermark, or visible grid lines\n"
        f"- do NOT crop feet, hair, or arms\n"
        f"- do NOT merge cells or create comic panels\n"
        f"- do NOT recenter the character differently per frame"
    )
    return gen("06-idle-south.png", prompt, "1536x1024", inputs=[neutral],
               subdir=ANIMS / "idle")


def step7_attack_spritesheet(neutral: Path) -> Path:
    """Generate attack animation — 5x2 grid, 10 frames."""
    print("\n" + "=" * 60)
    print("STEP 7: Attack Spritesheet (5x2, 10 frames)")
    print("=" * 60)

    prompt = (
        f"Create a 10-frame 5x2 spritesheet for a top-down 2D game character ATTACK animation.\n\n"
        f"Input images:\n"
        f"Image 1 is the identity anchor for {CHARACTER['name']}. Preserve the EXACT character "
        f"identity, outfit, proportions, palette, and south-facing direction.\n\n"
        f"Primary request:\n"
        f"Generate {CHARACTER['name']} performing a south-facing KEYBOARD SLAM attack. "
        f"The character raises both fists and slams them down (frustrated trader gesture). "
        f"Character faces SOUTH (toward camera) for every frame.\n\n"
        f"Canvas and layout:\n"
        f"- 1280x512 PNG spritesheet\n"
        f"- 5 columns by 2 rows\n"
        f"- ten equal 256x256 cells\n"
        f"- frame order: left to right across top row, then left to right across bottom row\n"
        f"- character fully visible in each cell, including both feet\n"
        f"- consistent character scale, camera, and ground baseline across all frames\n"
        f"- solid {CHROMA} chroma background\n\n"
        f"Frame sequence:\n"
        f"Frame 1: neutral ready stance, feet planted.\n"
        f"Frame 2: arms begin rising, slight lean back.\n"
        f"Frame 3: arms raised high, anticipation pose.\n"
        f"Frame 4: peak — fists at highest point, body stretched.\n"
        f"Frame 5: slam begins — arms swinging down fast.\n"
        f"Frame 6: IMPACT frame — fists hit desk level, small impact particles.\n"
        f"Frame 7: follow-through, body compressed from impact, small dust/spark.\n"
        f"Frame 8: recoil, bouncing back slightly.\n"
        f"Frame 9: settling, particles fade.\n"
        f"Frame 10: return to neutral stance.\n\n"
        f"Style:\n"
        f"- high-resolution pixel-art-inspired game sprite\n"
        f"- crisp edges, consistent lighting and palette: {CHARACTER['palette']}\n"
        f"- readable silhouette, dynamic but not over-the-top\n\n"
        f"Constraints:\n"
        f"- NO direction change between frames\n"
        f"- NO camera angle change\n"
        f"- NO extra characters, scenery, UI, labels, text, watermark\n"
        f"- do NOT crop feet, hair, or arms\n"
        f"- do NOT merge cells or create comic panels"
    )
    return gen("07-attack-south.png", prompt, "1536x1024", inputs=[neutral],
               subdir=ANIMS / "attack")


def step8_normalize():
    """Post-processing: chroma removal, foot anchoring, height normalization.

    This step uses Pillow to:
    1. Remove chroma background (#FF00FF) → transparent
    2. Find foot baseline (lowest non-transparent row)
    3. Align all frames to same baseline
    4. Crop to consistent bounding box
    """
    print("\n" + "=" * 60)
    print("STEP 8: Normalization (TODO — post-processing)")
    print("=" * 60)
    print("  After all generation is done, run normalize_v7.py to:")
    print("    - Remove chroma key background")
    print("    - Align foot baselines across all frames")
    print("    - Normalize height/centering")
    print("    - Export final runtime spritesheets")


def write_character_manifest():
    """Write character.json manifest (same format as chongdashu)."""
    manifest = {
        "version": 1,
        "id": "trader",
        "label": CHARACTER["name"],
        "frameWidth": 256,
        "frameHeight": 256,
        "defaultDirection": "s",
        "anchors": {
            "s": {
                "raw": "anchors/02-south-anchor.png",
                "neutral": "anchors/03-neutral-south.png",
            },
            "w": {"raw": "anchors/04-anchor-west.png"},
            "n": {"raw": "anchors/04-anchor-north.png"},
        },
        "animations": {
            "idle_s": "animations/idle/06-idle-south.png",
            "attack_s": "animations/attack/07-attack-south.png",
        },
        "pipeline": "anchor-chain-v7",
        "model": MODEL,
        "reference": "https://github.com/chongdashu/ai-game-spritesheets",
    }
    path = ROOT / "character.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  character.json written to {path}")


def main():
    print("=" * 60)
    print("V7 PIPELINE — Anchor Chain (chongdashu method)")
    print("=" * 60)
    print(f"  Model: {MODEL}")
    print(f"  Character: {CHARACTER['name']}")
    print(f"  Logical size: {LOGICAL_SIZE}")
    print(f"  Output size: {OUTPUT_SIZE}")
    print(f"  Chroma: {CHROMA}")

    # Step 1: Box Art
    box_art = step1_box_art()
    time.sleep(2)

    # Step 2: South Anchor (uses pixel grid, NOT box art as image input)
    south = step2_south_anchor(box_art)
    time.sleep(2)

    # Step 3: Neutral Anchor
    neutral = step3_neutral_anchor(south)
    time.sleep(2)

    # Step 4: Directional Anchors
    step4_directional_anchors(neutral)
    time.sleep(2)

    # Step 5: Walk (placeholder)
    step5_walk_placeholder()

    # Step 6: Idle
    step6_idle_spritesheet(neutral)
    time.sleep(2)

    # Step 7: Attack
    step7_attack_spritesheet(neutral)

    # Step 8: Normalize
    step8_normalize()

    # Write manifest
    write_character_manifest()

    print(f"\n{'=' * 60}")
    print("V7 PIPELINE COMPLETE")
    print(f"{'=' * 60}")
    print(f"\nOutputs in: {ROOT}")
    for f in sorted(ROOT.rglob("*.png")):
        rel = f.relative_to(ROOT)
        print(f"  {rel}: {f.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
