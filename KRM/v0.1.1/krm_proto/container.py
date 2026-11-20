"""KRM-IF v0.2 prototype container primitives.

Uncompressed, chunked, checksummed, and intentionally inspectable. This is
still a research format, not a frozen production file specification.
"""
from __future__ import annotations

import json
import os
import struct
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

from .pcm import pack_i64_planar, unpack_i64_planar

MAGIC = b"KRMIF\r\n\x1a"
MAJOR_VERSION = 0
MINOR_VERSION = 2
FILE_HEADER = struct.Struct("<8sHHI")
BLOCK_HEADER = struct.Struct("<4sIQIHHIIII")
BLOCK_MAGIC = b"BLK1"
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_CHANNELS = 32
MAX_SAMPLE_RATE_HZ = 768_000
MAX_SAMPLE_COUNT = (1 << 63) - 1
MAX_CHUNK_SAMPLES = 131_072
MIN_SUPPORTED_CONTAINER_REVISION = "prototype-0.1"
CURRENT_CONTAINER_REVISION = "prototype-0.2"

# Reflected Castagnoli polynomial.
_CRC32C_TABLE: tuple[int, ...] | None = None


def crc32c(data: bytes, crc: int = 0) -> int:
    global _CRC32C_TABLE
    if _CRC32C_TABLE is None:
        table = []
        for n in range(256):
            c = n
            for _ in range(8):
                c = (c >> 1) ^ (0x82F63B78 if c & 1 else 0)
            table.append(c & 0xFFFFFFFF)
        _CRC32C_TABLE = tuple(table)
    value = crc ^ 0xFFFFFFFF
    for byte in data:
        value = _CRC32C_TABLE[(value ^ byte) & 0xFF] ^ (value >> 8)
    return (value ^ 0xFFFFFFFF) & 0xFFFFFFFF


def canonical_json_bytes(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _require_int(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Invalid manifest field: {name}")
    return value


def validate_manifest(manifest: object, major: int, minor: int) -> dict:
    if not isinstance(manifest, dict):
        raise ValueError("KRM-IF manifest root must be a JSON object")
    if manifest.get("format") != "KRM-IF":
        raise ValueError("Unknown KRM-IF manifest identity")
    revision = manifest.get("container_revision")
    if revision not in (MIN_SUPPORTED_CONTAINER_REVISION, CURRENT_CONTAINER_REVISION):
        raise ValueError("Unknown KRM-IF container revision")
    if major != 0 or minor not in (1, 2):
        raise ValueError(f"Unsupported KRM-IF version {major}.{minor}")
    if (minor == 1 and revision != MIN_SUPPORTED_CONTAINER_REVISION) or (minor == 2 and revision != CURRENT_CONTAINER_REVISION):
        raise ValueError("KRM-IF header version and manifest revision disagree")

    audio = manifest.get("audio")
    container = manifest.get("container")
    reconstruction = manifest.get("reconstruction")
    if not isinstance(audio, dict) or not isinstance(container, dict) or not isinstance(reconstruction, dict):
        raise ValueError("KRM-IF manifest is missing required sections")
    if "base_provenance" in manifest and not isinstance(manifest["base_provenance"], dict):
        raise ValueError("KRM-IF base_provenance must be an object")

    channels = _require_int(audio.get("channels"), "audio.channels", 1, MAX_CHANNELS)
    rate = _require_int(audio.get("sample_rate_hz"), "audio.sample_rate_hz", 1, MAX_SAMPLE_RATE_HZ)
    sample_count = _require_int(audio.get("sample_count"), "audio.sample_count", 0, MAX_SAMPLE_COUNT)
    width = _require_int(audio.get("sample_width_bytes"), "audio.sample_width_bytes", 1, 4)
    if audio.get("sample_format") != "signed_integer_pcm":
        raise ValueError("Unsupported KRM-IF sample format")

    chunk_samples = _require_int(container.get("chunk_samples_per_channel"), "container.chunk_samples_per_channel", 1, MAX_CHUNK_SAMPLES)
    block_count = _require_int(container.get("block_count"), "container.block_count", 0, (1 << 32) - 1)
    expected_blocks = (sample_count + chunk_samples - 1) // chunk_samples
    if block_count != expected_blocks:
        raise ValueError("Manifest block count does not match sample count and chunk size")
    if container.get("payload_encoding") != "signed_int64_little_endian_channel_planar":
        raise ValueError("Unsupported KRM-IF payload encoding")
    if container.get("compression") != "none":
        raise ValueError("Unsupported KRM-IF compression")

    digest_fields = ["source_pcm_sha256", "base_pcm_sha256"]
    if minor >= 2:
        digest_fields.extend(["base_payload_sha256", "residual_payload_sha256"])
    for field in digest_fields:
        digest = reconstruction.get(field)
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            raise ValueError(f"Invalid reconstruction digest: {field}")

    # The caller checks the exact declared file size before block payload reads.
    # Per-block sample and channel limits cap each allocation.
    return manifest


def write_file_header(fp: BinaryIO, manifest: dict) -> int:
    """Write fixed header + manifest; return the manifest byte length."""
    payload = canonical_json_bytes(manifest)
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest exceeds prototype safety limit")
    fp.write(FILE_HEADER.pack(MAGIC, MAJOR_VERSION, MINOR_VERSION, len(payload)))
    fp.write(payload)
    return len(payload)


def patch_file_manifest(fp: BinaryIO, manifest: dict, expected_length: int) -> None:
    """Patch same-length digest fields without copying/re-writing the block body."""
    payload = canonical_json_bytes(manifest)
    if len(payload) != expected_length:
        raise ValueError("Final manifest changed length; refusing unsafe in-place patch")
    if len(payload) > MAX_MANIFEST_BYTES:
        raise ValueError("Manifest exceeds prototype safety limit")
    fp.seek(FILE_HEADER.size)
    fp.write(payload)
    fp.seek(0, os.SEEK_END)
    fp.flush()
    os.fsync(fp.fileno())


def read_file_header(fp: BinaryIO) -> tuple[dict, int, int]:
    raw = fp.read(FILE_HEADER.size)
    if len(raw) != FILE_HEADER.size:
        raise ValueError("Truncated KRM-IF file header")
    magic, major, minor, manifest_len = FILE_HEADER.unpack(raw)
    if magic != MAGIC:
        raise ValueError("Not a KRM-IF prototype file")
    if not 2 <= manifest_len <= MAX_MANIFEST_BYTES:
        raise ValueError("Invalid manifest length")
    payload = fp.read(manifest_len)
    if len(payload) != manifest_len:
        raise ValueError("Truncated KRM-IF manifest")
    def reject_non_finite(token: str):
        raise ValueError(f"Non-standard JSON numeric constant: {token}")
    try:
        manifest = json.loads(payload.decode("utf-8"), parse_constant=reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Invalid KRM-IF manifest JSON") from exc
    manifest = validate_manifest(manifest, major, minor)

    # Verify exact file size before any block payload allocation/read.
    here = fp.tell()
    fp.seek(0, os.SEEK_END)
    actual_size = fp.tell()
    fp.seek(here)
    audio = manifest["audio"]
    container = manifest["container"]
    channels = int(audio["channels"])
    sample_count = int(audio["sample_count"])
    block_count = int(container["block_count"])
    expected_size = FILE_HEADER.size + manifest_len + block_count * BLOCK_HEADER.size + channels * sample_count * 16
    if actual_size != expected_size:
        raise ValueError(f"KRM-IF file size mismatch: expected {expected_size}, got {actual_size}")
    return manifest, major, minor


def write_block(
    fp: BinaryIO,
    index: int,
    start_sample: int,
    sample_count: int,
    channels: int,
    base_channels: list[list[int]],
    residual_channels: list[list[int]],
    base_payload_hasher=None,
    residual_payload_hasher=None,
) -> tuple[int, int]:
    base_payload = pack_i64_planar(base_channels)
    residual_payload = pack_i64_planar(residual_channels)
    expected = channels * sample_count
    if len(base_payload) != expected * 8 or len(residual_payload) != expected * 8:
        raise ValueError("Block sample count mismatch")
    if base_payload_hasher is not None:
        base_payload_hasher.update(base_payload)
    if residual_payload_hasher is not None:
        residual_payload_hasher.update(residual_payload)
    fp.write(BLOCK_HEADER.pack(
        BLOCK_MAGIC, index, start_sample, sample_count, channels, 0,
        len(base_payload), len(residual_payload), crc32c(base_payload), crc32c(residual_payload)
    ))
    fp.write(base_payload)
    fp.write(residual_payload)
    return len(base_payload), len(residual_payload)


@dataclass
class Block:
    index: int
    start_sample: int
    sample_count: int
    channels: int
    base: list[list[int]]
    residual: list[list[int]]


def iter_blocks(fp: BinaryIO, manifest: dict) -> Iterator[Block]:
    channels = int(manifest["audio"]["channels"])
    total_samples = int(manifest["audio"]["sample_count"])
    chunk_size = int(manifest["container"]["chunk_samples_per_channel"])
    expected_blocks = int(manifest["container"]["block_count"])
    sample_width = int(manifest["audio"]["sample_width_bytes"])
    expected_start = 0
    for expected_index in range(expected_blocks):
        raw_header = fp.read(BLOCK_HEADER.size)
        if len(raw_header) != BLOCK_HEADER.size:
            raise ValueError(f"Truncated block header at block {expected_index}")
        (magic, index, start, count, block_channels, flags,
         base_len, residual_len, base_crc, residual_crc) = BLOCK_HEADER.unpack(raw_header)
        if magic != BLOCK_MAGIC or index != expected_index:
            raise ValueError(f"Invalid block marker/index at block {expected_index}")
        if flags != 0 or block_channels != channels:
            raise ValueError(f"Unsupported block flags/channel count at block {expected_index}")
        expected_count = min(chunk_size, total_samples - expected_start)
        if start != expected_start or count != expected_count or count < 1:
            raise ValueError(f"Invalid sample range at block {expected_index}")
        expected_payload_len = channels * count * 8
        if base_len != expected_payload_len or residual_len != expected_payload_len:
            raise ValueError(f"Invalid payload length at block {expected_index}")
        base_payload = fp.read(base_len)
        residual_payload = fp.read(residual_len)
        if len(base_payload) != base_len or len(residual_payload) != residual_len:
            raise ValueError(f"Truncated payload at block {expected_index}")
        if crc32c(base_payload) != base_crc:
            raise ValueError(f"BASE CRC-32C mismatch at block {expected_index}")
        if crc32c(residual_payload) != residual_crc:
            raise ValueError(f"RSDL CRC-32C mismatch at block {expected_index}")
        base = unpack_i64_planar(base_payload, channels, count)
        min_pcm = -(1 << (sample_width * 8 - 1)) if sample_width > 1 else -128
        max_pcm = (1 << (sample_width * 8 - 1)) - 1 if sample_width > 1 else 127
        if any(value < min_pcm or value > max_pcm for channel in base for value in channel):
            raise ValueError(f"BASE value outside declared PCM domain in block {expected_index}")
        yield Block(
            index=index,
            start_sample=start,
            sample_count=count,
            channels=channels,
            base=base,
            residual=unpack_i64_planar(residual_payload, channels, count),
        )
        expected_start += count
    if expected_start != total_samples:
        raise ValueError("Block table does not cover the declared sample count")
    if fp.read(1):
        raise ValueError("Unexpected trailing bytes after final KRM-IF block")


def atomic_output_path(path: str | Path) -> tuple[Path, Path]:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    return destination, temporary


def safe_replace(temporary: Path, destination: Path) -> None:
    os.replace(temporary, destination)
    # Best-effort directory sync makes the rename durable on POSIX filesystems.
    try:
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except (AttributeError, OSError):
        pass
