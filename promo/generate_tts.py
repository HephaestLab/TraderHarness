"""Generate narration MP3s for the TraderHarness promo via edge-tts.

Segments are 1:1 with scenes. Text is locked in DESIGN.md -- do not edit.
Outputs assets/audio/sN_*.mp3 and assets/audio/durations.json.
QC: each segment must be 3-35s; retry up to 3 attempts; fallback voice
zh-CN-YunxiNeural if YunjianNeural fails.
"""
import asyncio
import json
import sys
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

ROOT = Path(__file__).parent
OUT = ROOT / "assets" / "audio"
OUT.mkdir(parents=True, exist_ok=True)

SEGMENTS = [
    ("s0_hook", "给 Agent 做回测，至今没有规范。"),
    ("s1_pain", "通用模型，认得被测的日期、公司，甚至那段走势本身。泄漏，让评测悄悄失效；口径不一，让结果无法复现。"),
    ("s2_brand", "TraderHarness，就是这套规范——抗污染的 LLM 交易 Agent 回测环境。"),
    ("s3_proof", "时点掩码，让它认不出历史；唯一成交入口，真实价格结算；同样的输入，必然同样的结果。"),
    ("s4_data", "每一次运行，同时沉淀训练数据。指纹回放，一键导出。"),
    ("s5_cta", "TraderHarness。让每一次回测，值得被信任。"),
]

PRIMARY_VOICE = "zh-CN-YunxiNeural"
FALLBACK_VOICE = "zh-CN-YunjianNeural"
RATE = "-5%"
MIN_S, MAX_S = 2.0, 35.0  # v4: shorter hook script, min relaxed 3.0 -> 2.0


async def synth(text: str, voice: str, path: Path) -> None:
    comm = edge_tts.Communicate(text, voice, rate=RATE)
    await comm.save(str(path))


def duration(path: Path) -> float:
    return MP3(str(path)).info.length


async def main() -> None:
    durations = {}
    for name, text in SEGMENTS:
        target = OUT / f"{name}.mp3"
        ok = False
        for attempt in range(3):
            voice = PRIMARY_VOICE if attempt < 2 else FALLBACK_VOICE
            try:
                await synth(text, voice, target)
                d = duration(target)
                if MIN_S <= d <= MAX_S:
                    durations[name] = round(d, 3)
                    print(f"[ok] {name}: {d:.3f}s (voice={voice}, attempt={attempt + 1})", flush=True)
                    ok = True
                    break
                print(f"[qc-fail] {name}: {d:.3f}s out of range, retrying", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"[err] {name} attempt {attempt + 1} ({voice}): {e}", flush=True)
        if not ok:
            sys.exit(f"FAILED to produce QC-passing audio for {name}")

    with open(OUT / "durations.json", "w", encoding="utf-8") as f:
        json.dump(durations, f, ensure_ascii=False, indent=2)
    total = sum(durations.values())
    print(f"TOTAL narration: {total:.2f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
