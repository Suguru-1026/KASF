"""KRC adapters for exact integer-PCM residual capture."""
from __future__ import annotations

from collections.abc import Sequence as SequenceABC
import json
from pathlib import Path
from typing import Iterable, Sequence
import wave

from .pcm import WavSpec, decode_interleaved, read_wav_spec

DEFAULT_CHUNK_SAMPLES = 65_536
MAX_CHUNK_SAMPLES = 131_072


def _same_spec(source: WavSpec, base: WavSpec) -> None:
    if source != base:
        raise ValueError(
            "Source and Base PCM must have identical channels, sample rate, sample width, "
            "and sample count in this prototype. Resampling/projection is not implemented."
        )


def _same_path(left: str | Path, right: str | Path) -> bool:
    return Path(left).expanduser().resolve(strict=False) == Path(right).expanduser().resolve(strict=False)


def _validate_planar_chunk(
    chunk: Sequence[Sequence[int]], spec: WavSpec, expected_count: int, label: str
) -> list[list[int]]:
    if not isinstance(chunk, SequenceABC) or isinstance(chunk, (str, bytes, bytearray)) or len(chunk) != spec.channels:
        raise ValueError(f"{label} chunk channel count mismatch")
    result: list[list[int]] = []
    for channel_index, channel in enumerate(chunk):
        if len(channel) != expected_count:
            raise ValueError(f"{label} chunk {channel_index} sample count mismatch")
        values: list[int] = []
        for value in channel:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{label} PCM samples must be integers")
            if value < spec.min_value or value > spec.max_value:
                raise ValueError(f"{label} PCM sample outside declared bit-depth range")
            values.append(value)
        result.append(values)
    return result


def _build_manifest(spec: WavSpec, chunk_samples: int, base_provenance: dict | None = None) -> dict:
    total = spec.sample_count
    return {
        "format": "KRM-IF",
        "container_revision": "prototype-0.2",
        "created_by": "KRM Python Prototype 0.5",
        "purpose": "lossless integer-PCM residual research container",
        "base_provenance": base_provenance if base_provenance is not None else {
            "origin": "externally_supplied_canonical_pcm",
            "engine": None,
            "engine_revision": None,
            "reader_version": None,
            "normalization_policy": "not supplied by prototype adapter",
            "alignment": "identity_in_input_pcm_domain",
        },
        "audio": {
            "channels": spec.channels,
            "sample_rate_hz": spec.sample_rate,
            "sample_count": spec.sample_count,
            "sample_width_bytes": spec.sample_width,
            "sample_format": "signed_integer_pcm",
            "wav_pcm8_storage": "unsigned_on_disk_centered_to_signed_in_memory",
            "channel_layout": "explicit_channel_order_from_input_contract",
            "timebase": "integer_sample_index",
        },
        "container": {
            "chunk_samples_per_channel": chunk_samples,
            "block_count": (total + chunk_samples - 1) // chunk_samples,
            "payload_encoding": "signed_int64_little_endian_channel_planar",
            "compression": "none",
            "block_integrity": "CRC-32C",
            "source_and_base_digest": "SHA-256 of canonical interleaved PCM frame bytes",
            "payload_digest": "SHA-256 of concatenated signed-int64 little-endian planar block payloads",
        },
        "reconstruction": {
            "equation": "source_pcm = base_pcm + residual_pcm",
            "rounding": "none_after_integer_domain_alignment",
            "overflow_policy": "reject_if_reconstructed_value_outside_source_pcm_range",
            "source_pcm_sha256": "0" * 64,
            "base_pcm_sha256": "0" * 64,
            "base_payload_sha256": "0" * 64,
            "residual_payload_sha256": "0" * 64,
        },
        "limitations": [
            "Source and Base chunks must share the same sample domain and exact timeline",
            "the KRC writer performs no resampling, channel mapping, Reader emulation, normalization, or PCM quantization",
            "Base chunks must already be rendered in the declared Source PCM domain; canonical status is described by base_provenance and is never inferred",
            "this container is not a production KRM-IF specification",
        ],
    }


def capture_residual_chunks(
    source_chunks: Iterable[Sequence[Sequence[int]]],
    base_chunks: Iterable[Sequence[Sequence[int]]],
    spec: WavSpec,
    output_krmi: str | Path,
    chunk_samples: int = DEFAULT_CHUNK_SAMPLES,
    *,
    base_provenance: dict | None = None,
    resume: bool = False,
) -> dict:
    """Capture synchronized integer-PCM chunks with per-block checkpoints.

    Each stream item is channel-planar. Both iterators must begin at sample
    zero, use identical chunk boundaries, and contain exactly the declared
    sample count. With ``resume=True``, committed prefixes are replayed and
    compared to the partial KRM-IF file before capture continues.
    """
    from .resumable import capture_residual_chunks_resumable

    return capture_residual_chunks_resumable(
        source_chunks, base_chunks, spec, output_krmi, chunk_samples,
        base_provenance=base_provenance, resume=resume,
    )


def capture_residual(
    source_wav: str | Path,
    base_wav: str | Path,
    output_krmi: str | Path,
    chunk_samples: int = DEFAULT_CHUNK_SAMPLES,
    *,
    resume: bool = False,
    base_provenance: dict | None = None,
) -> dict:
    """WAV convenience adapter over :func:`capture_residual_chunks`."""
    if _same_path(output_krmi, source_wav) or _same_path(output_krmi, base_wav):
        raise ValueError("Output KRM-IF path must not overwrite Source or Base WAV")
    if isinstance(chunk_samples, bool) or not isinstance(chunk_samples, int) or not 1 <= chunk_samples <= MAX_CHUNK_SAMPLES:
        raise ValueError(f"chunk_samples must be between 1 and {MAX_CHUNK_SAMPLES}")

    with wave.open(str(source_wav), "rb") as src, wave.open(str(base_wav), "rb") as base:
        source_spec = read_wav_spec(src)
        base_spec = read_wav_spec(base)
        _same_spec(source_spec, base_spec)

        def source_chunks():
            while True:
                raw = src.readframes(chunk_samples)
                if not raw:
                    break
                yield decode_interleaved(raw, source_spec)

        def base_chunks():
            while True:
                raw = base.readframes(chunk_samples)
                if not raw:
                    break
                yield decode_interleaved(raw, base_spec)

        return capture_residual_chunks(
            source_chunks(), base_chunks(), source_spec, output_krmi,
            chunk_samples, base_provenance=base_provenance, resume=resume,
        )
