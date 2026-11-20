"""Recreate the Draft 0.5 10-second 48 kHz stereo benchmark WAV."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def main() -> None:
    output = Path(__file__).resolve().parent / "bench_48k_stereo.wav"
    rate = 48_000
    sample_count = rate * 10
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        buffer = bytearray()
        for i in range(sample_count):
            t = i / rate
            left = (
                0.34 * math.sin(2 * math.pi * (220 * t + 11 * t * t) + 0.2)
                + 0.17 * math.sin(2 * math.pi * 880 * t)
                + 0.06 * math.sin(2 * math.pi * 2400 * t)
            )
            right = (
                0.29 * math.sin(2 * math.pi * (330 * t + 7 * t * t) - 0.3)
                + 0.13 * math.sin(2 * math.pi * 990 * t + 0.5)
                + 0.05 * math.sin(2 * math.pi * 3100 * t)
            )
            l = max(-32768, min(32767, round(left * 32768)))
            r = max(-32768, min(32767, round(right * 32768)))
            buffer.extend(struct.pack("<hh", l, r))
            if len(buffer) >= 65_536:
                wav.writeframesraw(buffer)
                buffer.clear()
        if buffer:
            wav.writeframesraw(buffer)
    print(output)


if __name__ == "__main__":
    main()
