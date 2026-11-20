"""Create a small deterministic Source/Base PCM WAV pair for KRC testing."""
from __future__ import annotations
import math
import wave
from pathlib import Path


def write(path: Path, frames: list[tuple[int, int]], rate: int = 48000) -> None:
    import struct
    payload = bytearray()
    for left, right in frames:
        payload.extend(struct.pack("<hh", left, right))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(payload)


def main() -> None:
    root = Path("demo_audio")
    root.mkdir(exist_ok=True)
    rate, duration = 48000, 1.0
    source, base = [], []
    for n in range(int(rate * duration)):
        t = n / rate
        left = int(12000 * math.sin(2 * math.pi * 440 * t) + 1000 * math.sin(2 * math.pi * 1777 * t))
        right = int(9000 * math.sin(2 * math.pi * 660 * t))
        # A deliberately imperfect Base leaves a residual for the prototype.
        base_left = int(12000 * math.sin(2 * math.pi * 440 * t))
        base_right = int(9000 * math.sin(2 * math.pi * 660 * t))
        source.append((left, right))
        base.append((base_left, base_right))
    write(root / "source.wav", source, rate)
    write(root / "base.wav", base, rate)
    print(f"Created {root / 'source.wav'} and {root / 'base.wav'}")


if __name__ == "__main__":
    main()
