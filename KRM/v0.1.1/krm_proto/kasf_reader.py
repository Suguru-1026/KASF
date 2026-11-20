"""KASF v1 diagnostic decoder and bounded-memory pre-normalization Reader renderer.

This reproduces the audited KASF05_Reader local OLA formula. It is NOT a
production/canonical PCM export path: KASF v1 omits sample rate and sample
count, and KASF does not define a public float-to-integer PCM quantizer here.
"""
from __future__ import annotations

import math
import struct
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

HEADER = struct.Struct("<4sIQQd")
MAX_CHANNELS = 8
MAX_FRAMES = 1_000_000_000
MAX_COMPONENTS_PER_CHANNEL_FRAME = 100_000


def _js_round_positive(value: float) -> int:
    """JavaScript Math.round for non-negative Reader geometry values."""
    return math.floor(value + 0.5)


@dataclass(frozen=True)
class KASFHeader:
    channels: int
    frame_count: int
    frame_duration_s: float


def read_header(fp) -> KASFHeader:
    raw = fp.read(HEADER.size)
    if len(raw) != HEADER.size:
        raise ValueError("Truncated KASF v1 header")
    magic, version, channels, frames, duration = HEADER.unpack(raw)
    if magic != b"KASF" or version != 1:
        raise ValueError("Unsupported KASF header or version (expected KASF magic)")
    if not 1 <= channels <= MAX_CHANNELS or not 1 <= frames <= MAX_FRAMES:
        raise ValueError("Invalid KASF channel/frame count")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid KASF frame duration")
    return KASFHeader(channels, frames, duration)


def _read_frame(fp, channels: int):
    row = []
    for _ch in range(channels):
        raw_count = fp.read(8)
        if len(raw_count) != 8:
            raise ValueError("Truncated KASF component count")
        count = struct.unpack("<Q", raw_count)[0]
        if count > MAX_COMPONENTS_PER_CHANNEL_FRAME:
            raise ValueError("KASF component count exceeds safety limit")
        raw = fp.read(count * 6)
        if len(raw) != count * 6:
            raise ValueError("Truncated KASF component payload")
        comps = []
        for i in range(count):
            b0, b1, b2, b3, b4, b5 = raw[i*6:i*6+6]
            qf = b0 | (b1 << 8) | (b2 << 16)
            qa = b3 | ((b4 & 0x3F) << 8)
            qp = (b4 >> 6) | (b5 << 2)
            comps.append((qf / 0xFFFFFF * 96000.0, qa / 0x3FFF, qp * (2.0 * math.pi / 1024.0)))
        row.append(comps)
    return row


def _iter_frames(fp, header: KASFHeader):
    for _ in range(header.frame_count):
        yield _read_frame(fp, header.channels)
    if fp.read(1):
        raise ValueError("Unexpected trailing bytes after KASF frames")


def reader_geometry(header: KASFHeader, sample_rate_hz: int, sample_count: int):
    if isinstance(sample_rate_hz, bool) or not isinstance(sample_rate_hz, int) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be a positive integer side-metadata value")
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count < 0:
        raise ValueError("sample_count must be a non-negative integer side-metadata value")
    n = max(1, _js_round_positive(sample_rate_hz * header.frame_duration_s))
    h = max(1, _js_round_positive(sample_rate_hz * header.frame_duration_s / 2.0))
    if sample_count and (header.frame_count - 1) * h + n < sample_count:
        raise ValueError("KASF frames do not cover the declared sample_count")
    return n, h


def iter_reader_pcm_chunks(
    path: str | Path,
    *,
    sample_rate_hz: int,
    sample_count: int,
    chunk_samples: int = 65_536,
) -> Iterator[list[array]]:
    """Yield channel-planar float64 chunks from KASF05_Reader's OLA formula.

    Chunk boundaries do not reset overlap-add state. Accumulation order is
    frame -> sample -> component, matching KASF05_Reader.render's local path.
    Output is pre-any-external-normalization and is not integer PCM.
    """
    if isinstance(chunk_samples, bool) or not isinstance(chunk_samples, int) or chunk_samples < 1:
        raise ValueError("chunk_samples must be a positive integer")
    with open(path, "rb") as fp:
        header = read_header(fp)
        n, h = reader_geometry(header, sample_rate_hz, sample_count)
        capacity = n + h + 2
        ring = [[0.0] * capacity for _ in range(header.channels)]
        pending = [array('d') for _ in range(header.channels)]
        pending_count = 0
        cursor = 0
        hann = [0.5 - 0.5 * math.cos(2.0 * math.pi * i / n) for i in range(n)]

        def flush(until):
            nonlocal cursor, pending_count, pending
            while cursor < until:
                idx = cursor % capacity
                for ch in range(header.channels):
                    pending[ch].append(ring[ch][idx])
                    ring[ch][idx] = 0.0
                cursor += 1
                pending_count += 1
                if pending_count == chunk_samples:
                    out = pending
                    pending = [array('d') for _ in range(header.channels)]
                    pending_count = 0
                    yield out

        for m, frame in enumerate(_iter_frames(fp, header)):
            start = m * h
            for ch, comps in enumerate(frame):
                for local_n in range(n):
                    sample = start + local_n
                    if sample >= sample_count:
                        break
                    total = 0.0
                    for frequency, amplitude, phase in comps:
                        if amplitude > 0.0:
                            total += amplitude * math.sin(2.0 * math.pi * frequency * (local_n / sample_rate_hz) + phase)
                    ring[ch][sample % capacity] += hann[local_n] * total
            yield from flush(min((m + 1) * h, sample_count))

        yield from flush(sample_count)
        if pending_count:
            yield pending


def render_to_raw_f64(path: str | Path, output: str | Path, *, sample_rate_hz: int,
                      sample_count: int, chunk_samples: int = 65_536) -> dict:
    """Write interleaved little-endian float64 diagnostic PCM (not KRM Base PCM)."""
    import sys
    source_path = Path(path).resolve()
    output_path = Path(output).resolve()
    if source_path == output_path:
        raise ValueError("Output must not overwrite the KASF input")
    with open(source_path, "rb") as src:
        header = read_header(src)
    total = 0
    with open(output_path, "wb") as out:
        for chunk in iter_reader_pcm_chunks(source_path, sample_rate_hz=sample_rate_hz,
                                            sample_count=sample_count, chunk_samples=chunk_samples):
            count = len(chunk[0]) if chunk else 0
            interleaved = array('d')
            for i in range(count):
                for ch in range(header.channels):
                    interleaved.append(chunk[ch][i])
            if sys.byteorder != 'little':
                interleaved.byteswap()
            out.write(interleaved.tobytes())
            total += count
    return {"channels": header.channels, "sample_count_per_channel": total,
            "sample_rate_hz": sample_rate_hz, "sample_format": "float64_le_interleaved",
            "normalization": "none_applied", "canonical_krm_base": False}
