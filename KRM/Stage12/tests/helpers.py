from __future__ import annotations
import wave
from pathlib import Path
from krm_proto.pcm import WavSpec, encode_interleaved


def write_test_wav(path: Path, channels: list[list[int]], sample_rate: int, width: int) -> bytes:
    spec = WavSpec(len(channels), sample_rate, width, len(channels[0]) if channels else 0)
    raw = encode_interleaved(channels, spec)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(spec.channels)
        wav.setsampwidth(spec.sample_width)
        wav.setframerate(spec.sample_rate)
        wav.writeframes(raw)
    return raw
