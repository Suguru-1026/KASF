"""Crash-checkpointed KRC writer for the KRM-IF research prototype.

Commit ordering is: append one complete checksummed block -> fsync the partial
container -> atomically commit the journal. The journal therefore never points
past data that was durably written. Uncommitted tails are truncated on resume.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path
from typing import Iterable, Sequence

from .capture import _build_manifest, _validate_planar_chunk
from .container import (
    BLOCK_HEADER, BLOCK_MAGIC, FILE_HEADER, MAGIC, MAJOR_VERSION, MINOR_VERSION,
    canonical_json_bytes, crc32c, patch_file_manifest, safe_replace, write_block,
)
from .pcm import WavSpec, encode_interleaved, pack_i64_planar, unpack_i64_planar

JOURNAL_VERSION = 1


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except (AttributeError, OSError):
        pass


def _paths(destination: Path) -> tuple[Path, Path]:
    return (
        destination.with_name(destination.name + ".partial"),
        destination.with_name(destination.name + ".journal.json"),
    )


def _journal_document(payload: dict) -> dict:
    body = dict(payload)
    body["journal_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return body


def _write_journal(path: Path, payload: dict) -> None:
    raw = canonical_json_bytes(_journal_document(payload))
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.partial")
    try:
        with open(temporary, "xb") as fp:
            fp.write(raw)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _read_journal(path: Path) -> dict:
    try:
        raw = path.read_bytes()
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("KRC journal exceeds safety limit")
        obj = json.loads(raw.decode("utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("KRC checkpoint journal is unreadable") from exc
    if not isinstance(obj, dict):
        raise ValueError("KRC checkpoint journal root must be an object")
    digest = obj.pop("journal_sha256", None)
    if not isinstance(digest, str) or digest != hashlib.sha256(canonical_json_bytes(obj)).hexdigest():
        raise ValueError("KRC checkpoint journal integrity check failed")
    if obj.get("journal_version") != JOURNAL_VERSION:
        raise ValueError("Unsupported KRC checkpoint journal version")
    return obj


def _make_header(manifest: dict) -> bytes:
    payload = canonical_json_bytes(manifest)
    if not 2 <= len(payload) <= 16 * 1024 * 1024:
        raise ValueError("KRM-IF manifest length is outside supported limits")
    return FILE_HEADER.pack(MAGIC, MAJOR_VERSION, MINOR_VERSION, len(payload)) + payload


def _read_partial_block(fp, index: int, start_sample: int, count: int, channels: int, sample_width: int):
    raw_header = fp.read(BLOCK_HEADER.size)
    if len(raw_header) != BLOCK_HEADER.size:
        raise ValueError(f"Checkpoint block {index} header is truncated")
    (magic, actual_index, actual_start, actual_count, actual_channels, flags,
     base_len, residual_len, base_crc, residual_crc) = BLOCK_HEADER.unpack(raw_header)
    expected_payload_len = channels * count * 8
    if (magic != BLOCK_MAGIC or actual_index != index or actual_start != start_sample
            or actual_count != count or actual_channels != channels or flags != 0
            or base_len != expected_payload_len or residual_len != expected_payload_len):
        raise ValueError(f"Checkpoint block {index} geometry is invalid")
    base_payload = fp.read(base_len)
    residual_payload = fp.read(residual_len)
    if len(base_payload) != base_len or len(residual_payload) != residual_len:
        raise ValueError(f"Checkpoint block {index} payload is truncated")
    if crc32c(base_payload) != base_crc or crc32c(residual_payload) != residual_crc:
        raise ValueError(f"Checkpoint block {index} CRC-32C validation failed")
    base = unpack_i64_planar(base_payload, channels, count)
    residual = unpack_i64_planar(residual_payload, channels, count)
    lo = -128 if sample_width == 1 else -(1 << (sample_width * 8 - 1))
    hi = 127 if sample_width == 1 else (1 << (sample_width * 8 - 1)) - 1
    if any(value < lo or value > hi for channel in base for value in channel):
        raise ValueError(f"Checkpoint block {index} Base is outside declared PCM range")
    return base, residual, base_payload, residual_payload


def _validate_inputs(spec: WavSpec, chunk_samples: int, base_provenance: dict | None) -> None:
    values = (spec.channels, spec.sample_rate, spec.sample_width, spec.sample_count, chunk_samples)
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        raise ValueError("WavSpec and chunk size fields must be integers")
    if not 1 <= spec.channels <= 32 or not 1 <= spec.sample_rate <= 768_000:
        raise ValueError("WavSpec parameters are outside KRM prototype safety limits")
    if spec.sample_width not in (1, 2, 3, 4) or not 0 <= spec.sample_count <= (1 << 63) - 1:
        raise ValueError("WavSpec sample format or sample count is unsupported")
    if not 1 <= chunk_samples <= 131_072:
        raise ValueError("chunk_samples must be between 1 and 131072")
    if base_provenance is not None:
        if not isinstance(base_provenance, dict):
            raise ValueError("base_provenance must be a JSON-compatible object")
        try:
            json.dumps(base_provenance, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("base_provenance must contain JSON-compatible finite values") from exc


def capture_residual_chunks_resumable(
    source_chunks: Iterable[Sequence[Sequence[int]]],
    base_chunks: Iterable[Sequence[Sequence[int]]],
    spec: WavSpec,
    output_krmi: str | Path,
    chunk_samples: int = 65_536,
    *,
    base_provenance: dict | None = None,
    resume: bool = False,
) -> dict:
    """Write exact residual blocks with a sidecar journal and resume support.

    Both iterators must begin at sample zero, including during resume. Existing
    committed chunks are replayed and compared against both the Source and Base
    streams. A mismatch is rejected rather than silently continuing with a
    different recording, Reader revision, or normalization result.

    Checkpoint files are ``<output>.partial`` and ``<output>.journal.json``.
    They are retained after an exception so the caller can retry with
    ``resume=True``. A normal successful run removes the journal and atomically
    renames the partial file to the requested output path.
    """
    destination = Path(output_krmi).expanduser().resolve(strict=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial, journal_path = _paths(destination)
    _validate_inputs(spec, chunk_samples, base_provenance)
    if block_count := (spec.sample_count + chunk_samples - 1) // chunk_samples:
        if block_count > (1 << 32) - 1:
            raise ValueError("KRM-IF prototype block count exceeds uint32 indexing")
    else:
        block_count = 0

    manifest_template = _build_manifest(spec, chunk_samples, base_provenance)
    initial_header = _make_header(manifest_template)
    header_digest = hashlib.sha256(initial_header).hexdigest()
    has_partial = partial.exists()
    has_journal = journal_path.exists()
    if has_partial != has_journal:
        raise ValueError("Incomplete KRC checkpoint pair: .partial and .journal.json must both exist")
    if has_partial and not resume:
        raise FileExistsError("A KRC checkpoint already exists; pass resume=True or move it aside")
    if resume and has_partial:
        journal = _read_journal(journal_path)
        if journal.get("destination_name") != destination.name or journal.get("header_sha256") != header_digest:
            raise ValueError("KRC checkpoint belongs to a different output or capture configuration")
        committed_blocks = journal.get("committed_blocks")
        committed_samples = journal.get("committed_samples")
        committed_size = journal.get("committed_size")
        phase = journal.get("phase")
        if (isinstance(committed_blocks, bool) or not isinstance(committed_blocks, int)
                or not 0 <= committed_blocks <= block_count
                or isinstance(committed_samples, bool) or not isinstance(committed_samples, int)
                or isinstance(committed_size, bool) or not isinstance(committed_size, int)
                or phase not in ("CAPTURING", "FINALIZING")):
            raise ValueError("KRC checkpoint counters are invalid")
        expected_samples = min(spec.sample_count, committed_blocks * chunk_samples)
        if committed_samples != expected_samples:
            raise ValueError("KRC checkpoint sample counter is inconsistent")
        expected_size = len(initial_header)
        for i in range(committed_blocks):
            count = min(chunk_samples, spec.sample_count - i * chunk_samples)
            expected_size += BLOCK_HEADER.size + spec.channels * count * 16
        if committed_size != expected_size:
            raise ValueError("KRC checkpoint file-size counter is inconsistent")
        final_manifest = journal.get("final_manifest") if phase == "FINALIZING" else None
        if phase == "FINALIZING" and not isinstance(final_manifest, dict):
            raise ValueError("KRC finalization journal is missing its final manifest")
        with open(partial, "r+b") as fp:
            stored_header = fp.read(len(initial_header))
            allowed_headers = [initial_header]
            if final_manifest is not None:
                allowed_headers.append(_make_header(final_manifest))
            if stored_header not in allowed_headers:
                raise ValueError("KRC partial file header does not match its checkpoint journal")
            fp.seek(0, os.SEEK_END)
            actual_size = fp.tell()
            if actual_size < committed_size:
                raise ValueError("KRC partial file is shorter than its last committed checkpoint")
            if actual_size > committed_size:
                fp.truncate(committed_size)
                fp.flush()
                os.fsync(fp.fileno())
    else:
        committed_blocks = 0
        committed_samples = 0
        committed_size = len(initial_header)
        phase = "CAPTURING"
        final_manifest = None
        with open(partial, "xb") as fp:
            fp.write(initial_header)
            fp.flush()
            os.fsync(fp.fileno())
        journal = {
            "journal_version": JOURNAL_VERSION,
            "destination_name": destination.name,
            "header_sha256": header_digest,
            "committed_blocks": 0,
            "committed_samples": 0,
            "committed_size": len(initial_header),
            "phase": "CAPTURING",
            "final_manifest": None,
        }
        _write_journal(journal_path, journal)

    source_hash = hashlib.sha256()
    base_hash = hashlib.sha256()
    base_payload_hash = hashlib.sha256()
    residual_payload_hash = hashlib.sha256()
    source_iter = iter(source_chunks)
    base_iter = iter(base_chunks)
    sample_offset = 0

    try:
        # Re-read and cross-check all committed input blocks. hashlib state is
        # deliberately rebuilt from canonical input bytes; it is not serialized.
        with open(partial, "r+b") as out:
            out.seek(len(initial_header))
            for index in range(committed_blocks):
                expected_count = min(chunk_samples, spec.sample_count - sample_offset)
                try:
                    raw_source = next(source_iter)
                    raw_base = next(base_iter)
                except StopIteration as exc:
                    raise ValueError(f"Input stream ended while validating committed block {index}") from exc
                source_data = _validate_planar_chunk(raw_source, spec, expected_count, "Source")
                base_data = _validate_planar_chunk(raw_base, spec, expected_count, "Base")
                stored_base, stored_residual, base_payload, residual_payload = _read_partial_block(
                    out, index, sample_offset, expected_count, spec.channels, spec.sample_width
                )
                if stored_base != base_data:
                    raise ValueError(f"Base input differs from committed checkpoint block {index}")
                expected_residual = [
                    [source_data[ch][i] - base_data[ch][i] for i in range(expected_count)]
                    for ch in range(spec.channels)
                ]
                if stored_residual != expected_residual:
                    raise ValueError(f"Source input differs from committed checkpoint block {index}")
                source_hash.update(encode_interleaved(source_data, spec))
                base_hash.update(encode_interleaved(base_data, spec))
                base_payload_hash.update(base_payload)
                residual_payload_hash.update(residual_payload)
                sample_offset += expected_count

            out.seek(committed_size)
            for index in range(committed_blocks, block_count):
                expected_count = min(chunk_samples, spec.sample_count - sample_offset)
                try:
                    raw_source = next(source_iter)
                except StopIteration as exc:
                    raise ValueError(f"Source chunk stream ended before block {index}") from exc
                try:
                    raw_base = next(base_iter)
                except StopIteration as exc:
                    raise ValueError(f"Base chunk stream ended before block {index}") from exc
                source_data = _validate_planar_chunk(raw_source, spec, expected_count, "Source")
                base_data = _validate_planar_chunk(raw_base, spec, expected_count, "Base")
                source_hash.update(encode_interleaved(source_data, spec))
                base_hash.update(encode_interleaved(base_data, spec))
                residual_data = [
                    [source_data[ch][i] - base_data[ch][i] for i in range(expected_count)]
                    for ch in range(spec.channels)
                ]
                write_block(
                    out, index, sample_offset, expected_count, spec.channels,
                    base_data, residual_data,
                    base_payload_hasher=base_payload_hash,
                    residual_payload_hasher=residual_payload_hash,
                )
                out.flush()
                os.fsync(out.fileno())
                sample_offset += expected_count
                committed_blocks = index + 1
                committed_samples = sample_offset
                committed_size = out.tell()
                journal = {
                    "journal_version": JOURNAL_VERSION,
                    "destination_name": destination.name,
                    "header_sha256": header_digest,
                    "committed_blocks": committed_blocks,
                    "committed_samples": committed_samples,
                    "committed_size": committed_size,
                    "phase": "CAPTURING",
                    "final_manifest": None,
                }
                _write_journal(journal_path, journal)

            sentinel = object()
            if next(source_iter, sentinel) is not sentinel:
                raise ValueError("Source chunk stream contains extra data beyond declared sample count")
            if next(base_iter, sentinel) is not sentinel:
                raise ValueError("Base chunk stream contains extra data beyond declared sample count")

            manifest = manifest_template
            manifest["reconstruction"]["source_pcm_sha256"] = source_hash.hexdigest()
            manifest["reconstruction"]["base_pcm_sha256"] = base_hash.hexdigest()
            manifest["reconstruction"]["base_payload_sha256"] = base_payload_hash.hexdigest()
            manifest["reconstruction"]["residual_payload_sha256"] = residual_payload_hash.hexdigest()

            # Journal the final manifest before patching it. If power is lost
            # between these operations, resume accepts either header form and
            # verifies the input prefix again before finishing the rename.
            journal = {
                "journal_version": JOURNAL_VERSION,
                "destination_name": destination.name,
                "header_sha256": header_digest,
                "committed_blocks": committed_blocks,
                "committed_samples": committed_samples,
                "committed_size": committed_size,
                "phase": "FINALIZING",
                "final_manifest": manifest,
            }
            _write_journal(journal_path, journal)
            patch_file_manifest(out, manifest, len(canonical_json_bytes(manifest)))

        safe_replace(partial, destination)
        journal_path.unlink(missing_ok=True)
        _fsync_directory(destination.parent)
        return manifest
    except Exception:
        # The durable partial file and journal are intentionally retained.
        raise
