"""PCM/WAV helpers for the KRM research prototype (stdlib only)."""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import sys
import wave
from typing import Sequence


@dataclass(frozen=True)
class WavSpec:
    channels: int
    sample_rate: int
    sample_width: int
    sample_count: int

    @property
    def bit_depth(self) -> int:
        return self.sample_width * 8

    @property
    def min_value(self) -> int:
        if self.sample_width == 1:
            return -128
        return -(1 << (self.bit_depth - 1))

    @property
    def max_value(self) -> int:
        if self.sample_width == 1:
            return 127
        return (1 << (self.bit_depth - 1)) - 1


def read_wav_spec(wav: wave.Wave_read) -> WavSpec:
    if wav.getcomptype() != "NONE":
        raise ValueError("Only uncompressed PCM WAV is supported by this prototype")
    channels = wav.getnchannels()
    rate = wav.getframerate()
    width = wav.getsampwidth()
    count = wav.getnframes()
    if not 1 <= channels <= 32 or not 1 <= rate <= 768_000 or count < 0 or count > (1 << 63) - 1:
        raise ValueError("WAV parameters are outside the KRM prototype safety limits")
    if width not in (1, 2, 3, 4):
        raise ValueError(f"Unsupported PCM sample width: {width} bytes")
    return WavSpec(channels, rate, width, count)


def decode_interleaved(raw: bytes, spec: WavSpec) -> list[list[int]]:
    """Decode WAV interleaved PCM into channel-major signed integers."""
    frame_bytes = spec.channels * spec.sample_width
    if len(raw) % frame_bytes:
        raise ValueError("PCM byte count is not aligned to complete frames")
    count = len(raw) // frame_bytes
    out = [[] for _ in range(spec.channels)]
    width = spec.sample_width
    pos = 0
    for _ in range(count):
        for ch in range(spec.channels):
            b = raw[pos : pos + width]
            pos += width
            if width == 1:
                value = b[0] - 128  # WAV PCM8 is unsigned.
            else:
                value = int.from_bytes(b, "little", signed=True)
            out[ch].append(value)
    return out


def encode_interleaved(channels_data: Sequence[Sequence[int]], spec: WavSpec) -> bytes:
    if len(channels_data) != spec.channels:
        raise ValueError("Channel count mismatch")
    count = len(channels_data[0]) if channels_data else 0
    if any(len(ch) != count for ch in channels_data):
        raise ValueError("All channels must have the same sample count")
    lo, hi, width = spec.min_value, spec.max_value, spec.sample_width
    out = bytearray()
    for i in range(count):
        for ch in range(spec.channels):
            value = int(channels_data[ch][i])
            if value < lo or value > hi:
                raise OverflowError(f"PCM value {value} is outside [{lo}, {hi}]")
            if width == 1:
                out.append(value + 128)
            else:
                out.extend(value.to_bytes(width, "little", signed=True))
    return bytes(out)


def pack_i64_planar(channels_data: Sequence[Sequence[int]]) -> bytes:
    """Pack channel-major signed int64 samples in little-endian order."""
    values = [int(v) for channel in channels_data for v in channel]
    packed = array("q", values)
    if packed.itemsize != 8:
        raise RuntimeError("This platform does not provide 8-byte signed array('q')")
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def unpack_i64_planar(payload: bytes, channels: int, sample_count: int) -> list[list[int]]:
    expected = channels * sample_count * 8
    if len(payload) != expected:
        raise ValueError(f"Expected {expected} bytes of int64 data, got {len(payload)}")
    values = array("q")
    values.frombytes(payload)
    if values.itemsize != 8:
        raise RuntimeError("This platform does not provide 8-byte signed array('q')")
    if sys.byteorder != "little":
        values.byteswap()
    result = []
    cursor = 0
    for _ in range(channels):
        result.append(list(values[cursor : cursor + sample_count]))
        cursor += sample_count
    return result
