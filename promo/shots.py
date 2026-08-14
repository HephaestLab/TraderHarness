"""Screenshot each scene (via ?seek=<t> still-frame mode) into review/."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).parent
REVIEW = ROOT / "review"
REVIEW.mkdir(exist_ok=True)

# scene starts/durations mirror index.html timeline (v5 voiceover, Yunxi -5%)
DUR = [3.768, 11.880, 7.080, 9.624, 6.672, 5.328]
GAP = 0.12
S = [0.0]
for i in range(1, 6):
    S.append(S[-1] + DUR[i - 1] + GAP)
W3 = DUR[3] / 3

# midpoints + critical beats
SHOTS = {
    "v5_s0_first1s": S[0] + 0.9,      # product must be visible in 1st second
    "v5_s0_hook": S[0] + 2.8,
    "v5_s1_words": S[1] + 4.6,        # 日期/公司/走势本身 all shown
    "v5_s1_leak": S[1] + 5.9,         # dots backflowed into AGENT zone
    "v5_s1_drift": S[1] + 8.6,        # fingerprints drifting apart
    "v5_s1_norepro": S[1] + 10.4,     # 无法复现 caption
    "v5_s2_brand": S[2] + 2.4,
    "v5_s2_sub": S[2] + 4.6,          # subtitle visible
    "v5_s3_mask": S[3] + 1.6,         # mid mask sweep
    "v5_s3_gate": S[3] + W3 + 2.2,    # FILLED stamp
    "v5_s3_merge": S[3] + 2 * W3 + 2.6,  # merged fingerprint
    "v5_s4_lines": S[4] + 4.2,
    "v5_s5_title": S[5] + 2.0,
    "v5_s5_freeze": S[5] + DUR[5] + 2.0,
}


def main() -> None:
    only = sys.argv[1:] or None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
        for name, t in SHOTS.items():
            if only and name not in only:
                continue
            page.goto((ROOT / "index.html").as_uri() + f"?seek={t:.3f}")
            page.wait_for_function("window.__READY === true", timeout=15000)
            page.wait_for_timeout(350)
            out = REVIEW / f"{name}_{t:.2f}s.png"
            page.screenshot(path=str(out))
            print(f"[shot] {out.name}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
