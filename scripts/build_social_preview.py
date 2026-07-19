"""Compose the GitHub social preview from a generated pixel-office background."""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "assets" / "social-preview.png"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = ["seguisb.ttf" if bold else "segoeui.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    roots = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/truetype/dejavu")]
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("background", type=Path)
    args = parser.parse_args()

    with Image.open(args.background) as source:
        image = source.convert("RGB")
    target_ratio = 2.0
    current_ratio = image.width / image.height
    if current_ratio < target_ratio:
        crop_height = int(image.width / target_ratio)
        top = (image.height - crop_height) // 2
        image = image.crop((0, top, image.width, top + crop_height))
    else:
        crop_width = int(image.height * target_ratio)
        image = image.crop((0, 0, crop_width, image.height))
    image = image.resize((1280, 640), Image.Resampling.LANCZOS)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for x in range(740):
        alpha = int(235 * (1 - max(0, x - 400) / 340))
        draw.rectangle((x, 0, x + 1, 640), fill=(5, 9, 15, max(0, alpha)))

    draw.rectangle((68, 82, 114, 128), fill="#48d597")
    draw.text((80, 91), "TH", fill="#07100d", font=font(18, bold=True))
    draw.text((68, 174), "TraderHarness", fill="#f2f6f9", font=font(60, bold=True))
    draw.text((70, 258), "A market environment for", fill="#aab6c5", font=font(27))
    draw.text((70, 298), "autonomous trading agents.", fill="#aab6c5", font=font(27))
    draw.rectangle((70, 374, 112, 379), fill="#48d597")
    draw.text((70, 403), "POINT-IN-TIME  /  DUAL MASK  /  REPLAY", fill="#67ddb0", font=font(17, bold=True))
    draw.text((70, 472), "A-share backtesting · evaluation · SFT trajectories", fill="#7f8c9d", font=font(18))
    draw.text((70, 541), "github.com/HephaestLab/TraderHarness", fill="#c6d0dc", font=font(16))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB").save(OUTPUT, quality=94)
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
