"""KRM-IF prototype restore and verification."""
from __future__ import annotations

import hashlib
from pathlib import Path
import wave

from .container import atomic_output_path, iter_blocks, read_file_header, safe_replace
from .pcm import WavSpec, encode_interleaved, pack_i64_planar


def _spec_from_manifest(manifest: dict) -> WavSpec:
    a = manifest["audio"]
    return WavSpec(
        channels=int(a["channels"]),
        sample_rate=int(a["sample_rate_hz"]),
        sample_width=int(a["sample_width_bytes"]),
        sample_count=int(a["sample_count"]),
    )


def _reconstructed_channels(block, spec: WavSpec) -> list[list[int]]:
    channels = []
    for ch in range(spec.channels):
        values = [b + r for b, r in zip(block.base[ch], block.residual[ch])]
        if any(v < spec.min_value or v > spec.max_value for v in values):
            raise OverflowError(f"Reconstructed PCM outside allowed range in block {block.index}, channel {ch}")
        channels.append(values)
    return channels


def restore_krmi(input_krmi: str | Path, output_wav: str | Path) -> dict:
    import os

    destination, temporary = atomic_output_path(output_wav)
    if destination.resolve(strict=False) == Path(input_krmi).resolve(strict=False):
        raise ValueError("Output WAV path must not overwrite the input KRM-IF file")
    source_digest = hashlib.sha256()
    base_digest = hashlib.sha256()
    base_payload_digest = hashlib.sha256()
    residual_payload_digest = hashlib.sha256()
    try:
        with open(input_krmi, "rb") as fp:
            manifest, _, _ = read_file_header(fp)
            spec = _spec_from_manifest(manifest)
            data_bytes = spec.channels * spec.sample_count * spec.sample_width
            if data_bytes > 0xFFFFFFFF - 36:
                raise ValueError("Classic RIFF/WAV output would exceed its 4 GiB size limit; use restore-raw instead")
            with wave.open(str(temporary), "wb") as out:
                out.setnchannels(spec.channels)
                out.setsampwidth(spec.sample_width)
                out.setframerate(spec.sample_rate)
                out.setcomptype("NONE", "not compressed")
                samples_written = 0
                for block in iter_blocks(fp, manifest):
                    reconstructed = _reconstructed_channels(block, spec)
                    base_digest.update(encode_interleaved(block.base, spec))
                    base_payload_digest.update(pack_i64_planar(block.base))
                    residual_payload_digest.update(pack_i64_planar(block.residual))
                    raw = encode_interleaved(reconstructed, spec)
                    out.writeframesraw(raw)
                    source_digest.update(raw)
                    samples_written += block.sample_count
                if samples_written != spec.sample_count:
                    raise ValueError("Restored sample count mismatch")
        expected_source = manifest["reconstruction"].get("source_pcm_sha256")
        expected_base = manifest["reconstruction"].get("base_pcm_sha256")
        expected_base_payload = manifest["reconstruction"].get("base_payload_sha256")
        expected_residual_payload = manifest["reconstruction"].get("residual_payload_sha256")
        if expected_source and source_digest.hexdigest() != expected_source:
            raise ValueError("Restored PCM SHA-256 does not match the source digest")
        if expected_base and base_digest.hexdigest() != expected_base:
            raise ValueError("Stored Base PCM SHA-256 does not match the Base digest")
        if expected_base_payload and base_payload_digest.hexdigest() != expected_base_payload:
            raise ValueError("Stored Base payload SHA-256 mismatch")
        if expected_residual_payload and residual_payload_digest.hexdigest() != expected_residual_payload:
            raise ValueError("Stored Residual payload SHA-256 mismatch")
        safe_replace(temporary, destination)
        return {
            "samples": spec.sample_count,
            "channels": spec.channels,
            "sha256": source_digest.hexdigest(),
            "base_sha256": base_digest.hexdigest(),
            "base_payload_sha256": base_payload_digest.hexdigest(),
            "residual_payload_sha256": residual_payload_digest.hexdigest(),
            "matches_embedded_source_hash": bool(expected_source),
            "matches_embedded_base_hash": bool(expected_base),
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def restore_raw_pcm(input_krmi: str | Path, output_raw: str | Path) -> dict:
    """Restore interleaved canonical PCM bytes without a RIFF/WAV size limit."""
    destination, temporary = atomic_output_path(output_raw)
    if destination.resolve(strict=False) == Path(input_krmi).resolve(strict=False):
        raise ValueError("Output raw path must not overwrite the input KRM-IF file")
    source_digest = hashlib.sha256()
    base_digest = hashlib.sha256()
    base_payload_digest = hashlib.sha256()
    residual_payload_digest = hashlib.sha256()
    samples_written = 0
    try:
        with open(input_krmi, "rb") as fp:
            manifest, _, _ = read_file_header(fp)
            spec = _spec_from_manifest(manifest)
            with open(temporary, "wb") as out:
                for block in iter_blocks(fp, manifest):
                    reconstructed = _reconstructed_channels(block, spec)
                    base_digest.update(encode_interleaved(block.base, spec))
                    base_payload_digest.update(pack_i64_planar(block.base))
                    residual_payload_digest.update(pack_i64_planar(block.residual))
                    raw = encode_interleaved(reconstructed, spec)
                    out.write(raw)
                    source_digest.update(raw)
                    samples_written += block.sample_count
                if samples_written != spec.sample_count:
                    raise ValueError("Restored sample count mismatch")
                out.flush()
                import os
                os.fsync(out.fileno())
        expected = manifest["reconstruction"]
        expected_source = expected.get("source_pcm_sha256")
        expected_base = expected.get("base_pcm_sha256")
        expected_base_payload = expected.get("base_payload_sha256")
        expected_residual_payload = expected.get("residual_payload_sha256")
        if expected_source and source_digest.hexdigest() != expected_source:
            raise ValueError("Restored raw PCM SHA-256 does not match source digest")
        if expected_base and base_digest.hexdigest() != expected_base:
            raise ValueError("Restored raw Base PCM SHA-256 mismatch")
        if expected_base_payload and base_payload_digest.hexdigest() != expected_base_payload:
            raise ValueError("Restored raw Base payload SHA-256 mismatch")
        if expected_residual_payload and residual_payload_digest.hexdigest() != expected_residual_payload:
            raise ValueError("Restored raw Residual payload SHA-256 mismatch")
        safe_replace(temporary, destination)
        return {
            "samples_per_channel": spec.sample_count,
            "channels": spec.channels,
            "sample_rate_hz": spec.sample_rate,
            "sample_width_bytes": spec.sample_width,
            "byte_order": "little-endian",
            "interleaving": "frame-interleaved",
            "sha256": source_digest.hexdigest(),
            "matches_embedded_source_hash": bool(expected_source),
        }
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def verify_krmi(input_krmi: str | Path, source_wav: str | Path | None = None) -> dict:
    from .pcm import read_wav_spec

    with open(input_krmi, "rb") as fp:
        manifest, _, _ = read_file_header(fp)
        spec = _spec_from_manifest(manifest)
        reconstructed_hash = hashlib.sha256()
        base_hash = hashlib.sha256()
        base_payload_hash = hashlib.sha256()
        residual_payload_hash = hashlib.sha256()
        samples_checked = 0
        for block in iter_blocks(fp, manifest):
            reconstructed = _reconstructed_channels(block, spec)
            base_hash.update(encode_interleaved(block.base, spec))
            base_payload_hash.update(pack_i64_planar(block.base))
            residual_payload_hash.update(pack_i64_planar(block.residual))
            raw = encode_interleaved(reconstructed, spec)
            reconstructed_hash.update(raw)
            samples_checked += block.sample_count * spec.channels
        expected_source = manifest["reconstruction"].get("source_pcm_sha256")
        expected_base = manifest["reconstruction"].get("base_pcm_sha256")
        expected_base_payload = manifest["reconstruction"].get("base_payload_sha256")
        expected_residual_payload = manifest["reconstruction"].get("residual_payload_sha256")
        if expected_source and reconstructed_hash.hexdigest() != expected_source:
            raise ValueError("Reconstruction digest mismatch")
        if expected_base and base_hash.hexdigest() != expected_base:
            raise ValueError("Base PCM digest mismatch")
        if expected_base_payload and base_payload_hash.hexdigest() != expected_base_payload:
            raise ValueError("Base payload digest mismatch")
        if expected_residual_payload and residual_payload_hash.hexdigest() != expected_residual_payload:
            raise ValueError("Residual payload digest mismatch")

    source_matches = None
    if source_wav is not None:
        with wave.open(str(source_wav), "rb") as src:
            source_spec = read_wav_spec(src)
            if source_spec != spec:
                raise ValueError("Supplied source WAV metadata does not match KRM-IF")
            source_hash = hashlib.sha256()
            while True:
                raw = src.readframes(65_536)
                if not raw:
                    break
                source_hash.update(raw)
        source_matches = source_hash.hexdigest() == expected_source
        if not source_matches:
            raise ValueError("Supplied source WAV does not match the embedded source PCM digest")

    return {
        "status": "PASS",
        "samples_checked_including_channels": samples_checked,
        "source_pcm_sha256": expected_source,
        "reconstructed_pcm_sha256": reconstructed_hash.hexdigest(),
        "base_pcm_sha256": expected_base,
        "reconstructed_base_sha256": base_hash.hexdigest(),
        "base_payload_sha256": base_payload_hash.hexdigest(),
        "residual_payload_sha256": residual_payload_hash.hexdigest(),
        "matches_embedded_source_hash": bool(expected_source and reconstructed_hash.hexdigest() == expected_source),
        "matches_embedded_base_hash": bool(expected_base and base_hash.hexdigest() == expected_base),
        "supplied_source_matches": source_matches,
    }


def inspect_krmi(input_krmi: str | Path) -> dict:
    with open(input_krmi, "rb") as fp:
        manifest, major, minor = read_file_header(fp)
    return {"version": f"{major}.{minor}", **manifest}
