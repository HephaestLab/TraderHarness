"""Build the README animation from browser-captured product frames."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = ROOT / "docs" / "assets" / "demo-frames"
OUTPUT = ROOT / "docs" / "assets" / "traderharness-demo.gif"


def main() -> None:
    paths = sorted(FRAME_DIR.glob("*.png"))
    if not paths:
        raise SystemExit(f"No frames found in {FRAME_DIR}")
    frames = []
    for path in paths:
        with Image.open(path) as image:
            resized = image.convert("RGB").resize((960, 600), Image.Resampling.LANCZOS)
            frames.append(resized.quantize(colors=128, method=Image.Quantize.MEDIANCUT))
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=[1600, 2200, 1500, 2200, 2200, 2400][: len(frames)],
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
