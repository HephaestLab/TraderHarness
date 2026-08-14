"""Mux recorded webm + narration segments into out/traderharness-promo.mp4.

Pipeline: webm -> libx264/yuv420p/30fps mp4; narration mp3s concat with 0.15s
gaps (no BGM — silence is the design); loudnorm;
atrim+apad to exact video length (no bare -shortest). ffprobe verification:
video+audio streams must exist, duration diff < 0.1s.
"""
import json
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).parent
OUT = ROOT / "out"
AUDIO = ROOT / "assets" / "audio"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR = 48000

SEGS = ["s0_hook", "s1_pain", "s2_brand", "s3_proof", "s4_data", "s5_cta"]
GAP = 0.12  # v5: tightened so total lands in the 42-48s window


def run(cmd: list[str]) -> str:
    print("+", " ".join(str(c) for c in cmd[:6]), "...", flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:], flush=True)
        sys.exit(f"command failed: {cmd[0]}")
    return r.stderr


def ffprobe(path: Path) -> dict:
    exe = FFMPEG.replace("ffmpeg", "ffprobe")
    if not Path(exe).exists():
        # imageio-ffmpeg ships ffmpeg only; use ffmpeg -i fallback parsing
        r = subprocess.run([FFMPEG, "-i", str(path)], capture_output=True, text=True)
        return {"raw": r.stderr}
    r = subprocess.run(
        [exe, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True)
    return json.loads(r.stdout)


def detect_lead_in(webm: Path) -> float:
    """Find the first non-white frame (white hold = pre-start marker)."""
    r = subprocess.run(
        [FFMPEG, "-i", str(webm), "-vf", "signalstats,metadata=mode=print", "-an", "-f", "null", "-"],
        capture_output=True, text=True)
    pts, yavg = None, None
    seen_white = False
    import re
    for line in r.stderr.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            pts = float(m.group(1))
        m = re.search(r"lavfi\.signalstats\.YAVG=([\d.]+)", line)
        if m and pts is not None:
            yavg = float(m.group(1))
            if yavg > 200:
                seen_white = True
            elif seen_white and yavg < 100:
                return pts
    return 0.0


def main() -> None:
    webm = OUT / "video.webm"
    video_mp4 = OUT / "video_30fps.mp4"
    final = OUT / "traderharness-promo.mp4"

    with open(AUDIO / "durations.json", encoding="utf-8") as f:
        durs = json.load(f)
    total = sum(durs[s] for s in SEGS) + GAP * (len(SEGS) - 1) + 3.0  # v4 freeze 3.0s
    print(f"[mux] timeline total: {total:.3f}s", flush=True)

    # 1) trim white lead-in + tail, webm -> mp4 30fps yuv420p
    lead = detect_lead_in(webm)
    print(f"[mux] white lead-in: {lead:.3f}s", flush=True)
    run([FFMPEG, "-y", "-ss", f"{lead:.3f}", "-t", f"{total:.3f}", "-i", webm,
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", "30", "-an", video_mp4])

    # video duration via ffmpeg -i parse
    info = ffprobe(video_mp4)
    if "format" in info:
        vd = float(info["format"]["duration"])
    else:
        import re
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info["raw"])
        vd = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    print(f"[mux] video duration: {vd:.3f}s", flush=True)

    # 2) narration concat (0.15s gaps) + loudnorm -> narration_mix.wav (no BGM)
    inputs: list[str] = []
    for s in SEGS:
        inputs += ["-i", str(AUDIO / f"{s}.mp3")]
    for _ in range(len(SEGS) - 1):
        inputs += ["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo:d={GAP}"]
    # concat order: s0, gap, s1, gap, ..., s5  -> input indexes 0..10
    concat_in = "".join(f"[{i}:a]" for i in range(2 * len(SEGS) - 1))
    fc = (f"{concat_in}concat=n={2 * len(SEGS) - 1}:v=0:a=1[narr];"
          f"[narr]aformat=sample_rates={SR}:channel_layouts=stereo[narr2];"
          f"[narr2]loudnorm=I=-16:TP=-1.5:LRA=11[mixout]")
    narr_wav = OUT / "narration_mix.wav"
    run([FFMPEG, "-y", *inputs, "-filter_complex", fc, "-map", "[mixout]",
         "-ar", str(SR), "-ac", "2", narr_wav])

    # 4) mux with atrim+apad to exact video length
    samples = int(round(vd * SR))
    fc2 = (f"[1:a]atrim=start=0:duration={vd:.3f},asetpts=PTS-STARTPTS,"
           f"apad=whole_len={samples}[aout]")
    run([FFMPEG, "-y", "-i", video_mp4, "-i", narr_wav, "-filter_complex", fc2,
         "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         final])

    # 5) verify
    info = ffprobe(final)
    ok = False
    if "streams" in info:
        kinds = [s["codec_type"] for s in info["streams"]]
        vdur = float(next(s for s in info["streams"] if s["codec_type"] == "video")["duration"])
        adur = float(next(s for s in info["streams"] if s["codec_type"] == "audio")["duration"])
        print(f"[verify] streams={kinds} video={vdur:.3f}s audio={adur:.3f}s diff={abs(vdur-adur):.3f}s", flush=True)
        ok = "video" in kinds and "audio" in kinds and abs(vdur - adur) < 0.1
    else:
        raw = info["raw"]
        has_v = "Video:" in raw
        has_a = "Audio:" in raw
        print(f"[verify-fallback] video={has_v} audio={has_a}", flush=True)
        import re
        m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", raw)
        d = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
        ok = has_v and has_a and abs(d - vd) < 0.15
    if not ok:
        sys.exit("VERIFY FAILED")
    print(f"[done] {final}", flush=True)


if __name__ == "__main__":
    main()
