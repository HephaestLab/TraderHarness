"""Build the README animation from browser-captured product frames.

Frames come from `webui/scripts/capture-demo.mjs` (docs/assets/demo-frames).
The GIF targets the README hero slot: ~920px wide, sub-second frame pacing,
small enough to stay pleasant on slower connections (<1.5 MB ideally).
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = ROOT / "docs" / "assets" / "demo-frames"
OUTPUT = ROOT / "docs" / "assets" / "traderharness-demo.gif"

WIDTH = 920
# Frames that repeat a beat already covered by a neighbouring frame.
SKIP = {"05-demo-dossier.png"}
# Per-frame hold time (ms); defaults to 750 for anything unlisted.
DURATIONS = {
    "01-dashboard.png": 800,
    "02-live-early.png": 600,
    "03-live-mid.png": 700,
    "04-live-done.png": 900,
    "06-compare-overview.png": 800,
    "07-trade-review.png": 800,
    "08-overview.png": 800,
    "09-library-select.png": 700,
    "10-run-compare.png": 900,
}


def main() -> None:
    paths = sorted(FRAME_DIR.glob("*.png"))
    paths = [path for path in paths if path.name not in SKIP]
    if not paths:
        raise SystemExit(f"No frames found in {FRAME_DIR}")
    frames = []
    durations = []
    for path in paths:
        with Image.open(path) as image:
            image = image.convert("RGB")
            height = round(image.height * WIDTH / image.width)
            resized = image.resize((WIDTH, height), Image.Resampling.LANCZOS)
            frames.append(resized.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
            durations.append(DURATIONS.get(path.name, 750))
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes, {len(frames)} frames)")


if __name__ == "__main__":
    main()
