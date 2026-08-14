"""Record index.html in real time with Playwright -> webm."""
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
REC_DIR = ROOT / "recording"
OUT_WEBM = ROOT / "out" / "video.webm"
TOTAL = 48.0  # scene timeline total (s); timeout has margin


def main() -> None:
    REC_DIR.mkdir(exist_ok=True)
    (ROOT / "out").mkdir(exist_ok=True)
    for old in REC_DIR.glob("*.webm"):
        old.unlink()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[
            "--disable-gpu-vsync", "--disable-frame-rate-limit",
            "--autoplay-policy=no-user-gesture-required",
        ])
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            device_scale_factor=1,
            record_video_dir=str(REC_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = ctx.new_page()
        page.goto((ROOT / "index.html").as_uri())
        page.wait_for_function("window.__READY === true", timeout=15000)
        page.wait_for_timeout(400)  # let the white hold frame reach the recorder
        t0 = time.time()
        page.evaluate("window.__START()")
        page.wait_for_function("window.__DONE === true", timeout=int(TOTAL * 1000) + 45000)
        print(f"[record] finished in {time.time() - t0:.1f}s wall", flush=True)
        video = page.video
        ctx.close()
        browser.close()
        src = Path(video.path())
        shutil.move(str(src), str(OUT_WEBM))
        print(f"[record] saved {OUT_WEBM}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
