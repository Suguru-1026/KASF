"""Native C++ KASF v1 spectral-pursuit generator and KRM bridge.

The generator writes the KASF v1 container and quantized 24/14/10-bit
components. It is a fast baseline, not a copy of the full Rev.0.9.20 encoder.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from .capture import capture_residual
from .kasf_reader import iter_reader_pcm_chunks, read_header
from .pcm import encode_interleaved, read_wav_spec

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CPP_SOURCE = Path(__file__).resolve().parent / "native" / "kasf_fastgen.cpp"
DEFAULT_BINARY = Path(__file__).resolve().parent / "native" / "bin" / ("kasf_fastgen.exe" if os.name == "nt" else "kasf_fastgen")
METADATA_FORMAT = "KASF-FastGen-Metadata"
PCM_QUANTIZER = "KRM-PROTO-PCM-Q-v1: signed PCM scale=2^(bits-1), JS-Math.round-compatible floor(x+0.5), saturating"


def sha256_file(path: str | Path, chunk_bytes: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fp:
        while True:
            block = fp.read(chunk_bytes)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def build_native(output: str | Path | None = None, compiler: str | None = None) -> Path:
    """Build the C++17 generator with the available GCC/Clang compiler."""
    cc = compiler or os.environ.get("CXX") or shutil.which("g++") or shutil.which("clang++")
    if not cc:
        raise RuntimeError("A C++17 compiler (g++ or clang++) is required to build KASF FastGen")
    target = Path(output) if output else DEFAULT_BINARY
    target.parent.mkdir(parents=True, exist_ok=True)
    cmd = [cc, "-O3", "-std=c++17", "-ffp-contract=off", "-DNDEBUG", str(CPP_SOURCE), "-o", str(target)]
    completed = subprocess.run(cmd, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(
            "Native KASF FastGen build failed:\n" + completed.stdout + completed.stderr
        )
    return target


def _source_spec(path: str | Path) -> WavSpec:
    with wave.open(str(path), "rb") as wav:
        return read_wav_spec(wav)


def generate_kasf(
    input_wav: str | Path,
    output_kasf: str | Path,
    *,
    frame_ms: float = 10.0,
    max_components: int = 48,
    threshold_db: float = -58.0,
    min_hz: float = 15.0,
    edge_pad: bool = True,
    temporal_tracking: bool = True,
    temporal_refinement: bool = False,
    tracker_assignment: str = "greedy",
    base_wav: str | Path | None = None,
    force: bool = False,
    binary: str | Path | None = None,
) -> dict:
    """Generate KASF v1 and, optionally, render its local Reader Base in native C++."""
    source = Path(input_wav).expanduser().resolve()
    output = Path(output_kasf).expanduser().resolve()
    base = Path(base_wav).expanduser().resolve() if base_wav is not None else None
    if tracker_assignment not in {"greedy", "hungarian"}:
        raise ValueError("tracker_assignment must be greedy or hungarian")
    if source == output or (base is not None and (base == source or base == output)):
        raise ValueError("Source, KASF output, and optional Base WAV paths must be distinct")
    if not source.is_file():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not force:
        raise FileExistsError(f"Output exists: {output}; pass force=True to replace it")
    track_map = output.with_suffix(output.suffix + ".tracks.jsonl") if temporal_tracking else None
    if track_map is not None and track_map.exists() and not force:
        raise FileExistsError(f"Track map exists: {track_map}; pass force=True to replace it")
    if base is not None and base.exists() and not force:
        raise FileExistsError(f"Base WAV exists: {base}; pass force=True to replace it")
    if base is not None:
        base.parent.mkdir(parents=True, exist_ok=True)
    exe = Path(binary).resolve() if binary else DEFAULT_BINARY
    if not exe.is_file() or CPP_SOURCE.stat().st_mtime_ns > exe.stat().st_mtime_ns:
        exe = build_native(exe)
    command = [
        str(exe), str(source), str(output), "--frame-ms", str(frame_ms),
        "--max-components", str(max_components), "--threshold-db", str(threshold_db),
        "--min-hz", str(min_hz),
    ]
    if edge_pad:
        command.append("--edge-pad")
    if not temporal_tracking:
        command.append("--no-tracking")
    elif track_map is not None:
        command.extend(["--track-map", str(track_map)])
    command.extend(["--tracker-assignment", tracker_assignment])
    if temporal_refinement:
        command.append("--experimental-track-refine")
    if base is not None:
        command.extend(["--base-wav", str(base)])
    if force:
        command.append("--force")
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError("KASF FastGen failed:\n" + completed.stdout + completed.stderr)
    try:
        stats = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Generator returned invalid status JSON: {completed.stdout!r}") from exc
    spec = _source_spec(source)
    if (stats["channels"], stats["sample_rate_hz"], stats["sample_count"]) != (
        spec.channels, spec.sample_rate, spec.sample_count
    ):
        raise RuntimeError("Generator WAV metadata does not match Python WAV reader")
    with open(output, "rb") as fp:
        header = read_header(fp)
    if header.channels != spec.channels or header.frame_count != stats["frame_count"]:
        raise RuntimeError("Generated KASF header verification failed")
    track_info = None
    if track_map is not None:
        if not track_map.is_file() or not stats.get("track_map_written"):
            raise RuntimeError("Temporal tracking was enabled but its track map was not written")
        expected_rows = stats["frame_count"] * spec.channels
        with track_map.open("r", encoding="utf-8") as fp:
            row_count = sum(1 for line in fp if line.strip())
        if row_count != expected_rows:
            raise RuntimeError(f"Track map has {row_count} rows; expected {expected_rows}")
        track_info = {
            "path": str(track_map),
            "sha256": sha256_file(track_map),
            "row_count": row_count,
            "format": "KASF-TrackMap-JSONL-v1",
        }
    base_info = None
    if base is not None:
        if not base.is_file() or not stats.get("base_wav_written"):
            raise RuntimeError("Native generator did not produce the requested Base WAV")
        base_spec = _source_spec(base)
        if base_spec != spec:
            raise RuntimeError(f"Native Base WAV parameters {base_spec} do not match Source {spec}")
        base_info = {
            "base_wav": str(base),
            "base_wav_sha256": sha256_file(base),
            "channels": base_spec.channels,
            "sample_rate_hz": base_spec.sample_rate,
            "sample_count": base_spec.sample_count,
            "sample_width_bytes": base_spec.sample_width,
            "normalization": "none",
            "integer_pcm_quantizer": PCM_QUANTIZER,
            "reader_frame_size": stats["frame_size"],
            "reader_hop_samples": stats["hop_samples"],
            "edge_padding_samples_each_side": stats["edge_padding_samples"],
            "reader_timeline_sample_count": stats["analysis_timeline_sample_count"],
            "base_is_official_kasf_pcm_export": False,
            "renderer": "C++ FastGen embedded KASF05_Reader-equivalent OLA loop",
        }
    metadata = {
        "format": METADATA_FORMAT,
        "metadata_version": 2,
        "source_wav": str(source),
        "source_wav_sha256": sha256_file(source),
        "kasf_file": str(output),
        "kasf_sha256": sha256_file(output),
        "audio": {
            "channels": spec.channels,
            "sample_rate_hz": spec.sample_rate,
            "sample_count": spec.sample_count,
            "sample_width_bytes": spec.sample_width,
            "channel_order": "WAV channel order preserved",
            "resampling": "none; source sample rate retained",
        },
        "generator": {
            "name": "KASF Fast Baseline Generator",
            "version": "0.3.0",
            "algorithm": "per-frame Hann-windowed radix-2 FFT peak picking + parabolic log-magnitude interpolation + weighted sine/cosine least-squares fit + quantized residual pursuit",
            "temporal_tracking": {
                "enabled": bool(stats.get("temporal_tracking_enabled", temporal_tracking)),
                "method": f"{tracker_assignment} one-to-one frame association using predicted frequency, phase advance, and amplitude continuity",
                "assignment": str(stats.get("temporal_tracker_assignment", tracker_assignment)),
                "max_missing_frames": 2,
                "payload_modification_default": False,
                "track_map": track_info,
                "experimental_refinement_enabled": bool(stats.get("temporal_refinement_enabled", False)),
                "experimental_refinement_note": "disabled by default; prior synthetic tests found reduced Base SNR in mixed signals",
                "experimental_refinement_formula": "phase-unwrapped average frequency with symmetric-window center phase compensation",
            },
            "frame_duration_ms": float(frame_ms),
            "max_components_per_channel_frame": int(max_components),
            "threshold_dbfs": float(threshold_db),
            "minimum_frequency_hz": float(min_hz),
            "edge_padding_samples_each_side": int(stats.get("edge_padding_samples", 0)),
            "analysis_timeline_sample_count": int(stats.get("analysis_timeline_sample_count", spec.sample_count)),
            "compiler_binary": str(exe),
            "limitations": [
                "baseline encoder; does not implement full Rev.0.9.20 STN/HPSS/Matrix Pencil/NOMP/ADMM/TVS/TCE/KASE optimization stages",
                "temporal matching is a local frequency/phase/amplitude association, not a perceptual source tracker",
                "does not implement worker phase-seam correction or full KASE component optimization",
                "no source resampling; source rate and sample count are carried in this sidecar",
                "KASF v1 stores no source rate/sample count; retain this sidecar with the file",
            ],
        },
        "reader_bridge": {
            "reader": "Rev.0.9.20 KASF05_Reader local OLA equation",
            "normalization": "none applied; the local Reader is pre any external/global normalization policy",
            "timeline_crop": "discard leading/trailing guard samples and retain the original source timeline" if edge_pad else "identity timeline",
            "integer_pcm_quantizer": PCM_QUANTIZER,
            "canonical_kasf_export": False,
            "native_base_wav": base_info,
        },
        "generator_stats": stats,
        "track_map": track_info,
    }
    sidecar = output.with_suffix(output.suffix + ".meta.json")
    tmp = sidecar.with_suffix(sidecar.suffix + ".part")
    tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, sidecar)
    return {"output": str(output), "metadata": str(sidecar), "base_wav": base_info, **stats}


def _quantize_to_pcm(value: float, spec: WavSpec) -> int:
    if not math.isfinite(value):
        value = 0.0
    scale = 1 << (spec.bit_depth - 1)
    q = math.floor(value * scale + 0.5)  # JavaScript Math.round-compatible for finite values.
    return max(spec.min_value, min(spec.max_value, q))


def render_kasf_to_base_wav(
    input_kasf: str | Path,
    source_wav: str | Path,
    base_wav: str | Path,
    *,
    chunk_samples: int = 65_536,
) -> dict:
    """Render the local KASF Reader equation and quantize to Source PCM format.

    The quantizer is explicitly KRM-prototype policy, not an official KASF v1
    integer PCM export rule. No global normalization is applied.
    """
    kasf = Path(input_kasf).expanduser().resolve()
    source = Path(source_wav).expanduser().resolve()
    base = Path(base_wav).expanduser().resolve()
    if base in (kasf, source):
        raise ValueError("Base WAV output must not overwrite KASF or Source input")
    if base.exists():
        raise FileExistsError(f"Base WAV already exists: {base}")
    spec = _source_spec(source)
    if not 1 <= spec.channels <= 8:
        raise ValueError("KASF Fast bridge supports 1..8 channels")
    with open(kasf, "rb") as fp:
        header = read_header(fp)
    if header.channels != spec.channels:
        raise ValueError("KASF channel count does not match Source WAV")
    frame_duration = header.frame_duration_s
    n = max(1, math.floor(spec.sample_rate * frame_duration + 0.5))
    h = max(1, math.floor(spec.sample_rate * frame_duration / 2.0 + 0.5))
    sidecar = kasf.with_suffix(kasf.suffix + ".meta.json")
    edge_pad = 0
    timeline_count = spec.sample_count
    if sidecar.is_file():
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
        audio_meta = meta.get("audio", {})
        if (audio_meta.get("channels"), audio_meta.get("sample_rate_hz"), audio_meta.get("sample_count")) != (spec.channels, spec.sample_rate, spec.sample_count):
            raise ValueError("KASF sidecar Source timeline does not match Source WAV")
        gen_meta = meta.get("generator", {})
        edge_pad = int(gen_meta.get("edge_padding_samples_each_side", 0))
        timeline_count = int(gen_meta.get("analysis_timeline_sample_count", spec.sample_count))
    if timeline_count != spec.sample_count + 2 * edge_pad:
        raise ValueError("Invalid KASF edge-padding timeline in metadata")
    if (header.frame_count - 1) * h + n < timeline_count:
        raise ValueError("KASF frames do not cover the declared Reader timeline")
    base.parent.mkdir(parents=True, exist_ok=True)
    tmp = base.with_suffix(base.suffix + ".part")
    try:
        with wave.open(str(tmp), "wb") as dst:
            dst.setnchannels(spec.channels)
            dst.setsampwidth(spec.sample_width)
            dst.setframerate(spec.sample_rate)
            written = 0
            samples_to_skip = edge_pad
            samples_to_keep = spec.sample_count
            for chunk in iter_reader_pcm_chunks(
                kasf, sample_rate_hz=spec.sample_rate,
                sample_count=timeline_count, chunk_samples=chunk_samples,
            ):
                count = len(chunk[0]) if chunk else 0
                start = min(samples_to_skip, count)
                samples_to_skip -= start
                take = min(samples_to_keep, count - start)
                if take <= 0:
                    continue
                channels_int = [
                    [_quantize_to_pcm(float(v), spec) for v in chunk[ch][start:start + take]]
                    for ch in range(spec.channels)
                ]
                dst.writeframesraw(encode_interleaved(channels_int, spec))
                written += take
                samples_to_keep -= take
            if samples_to_skip or samples_to_keep:
                raise RuntimeError("Reader guard crop did not produce the requested source timeline")
            if written != spec.sample_count:
                raise RuntimeError(f"Reader emitted {written} samples; expected {spec.sample_count}")
        os.replace(tmp, base)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return {
        "base_wav": str(base),
        "channels": spec.channels,
        "sample_rate_hz": spec.sample_rate,
        "sample_count": spec.sample_count,
        "sample_width_bytes": spec.sample_width,
        "reader_frame_size": n,
        "reader_hop_samples": h,
        "edge_padding_samples_each_side": edge_pad,
        "reader_timeline_sample_count": timeline_count,
        "normalization": "none",
        "integer_pcm_quantizer": PCM_QUANTIZER,
        "base_is_official_kasf_pcm_export": False,
    }


def generate_and_capture(
    source_wav: str | Path,
    output_kasf: str | Path,
    output_base_wav: str | Path,
    output_krmi: str | Path,
    *,
    frame_ms: float = 10.0,
    max_components: int = 48,
    threshold_db: float = -58.0,
    min_hz: float = 15.0,
    edge_pad: bool = True,
    temporal_tracking: bool = True,
    temporal_refinement: bool = False,
    tracker_assignment: str = "greedy",
    chunk_samples: int = 65_536,
    force: bool = False,
    resume: bool = False,
    binary: str | Path | None = None,
) -> dict:
    """Run FastGen -> local Reader Base -> KRC capture, with resumable KRC capture."""
    if tracker_assignment not in {"greedy", "hungarian"}:
        raise ValueError("tracker_assignment must be greedy or hungarian")
    source = Path(source_wav).resolve()
    kasf = Path(output_kasf).resolve()
    base = Path(output_base_wav).resolve()
    krmi = Path(output_krmi).resolve()
    if len({source, kasf, base, krmi}) != 4:
        raise ValueError("Source, KASF, Base WAV, and KRM-IF paths must all be distinct")
    partial = krmi.with_name(krmi.name + ".partial")
    journal = krmi.with_name(krmi.name + ".journal.json")
    metadata_path = kasf.with_suffix(kasf.suffix + ".meta.json")
    if force and resume:
        raise ValueError("force and resume are mutually exclusive")
    if resume:
        if krmi.exists():
            raise FileExistsError(f"KRM-IF is already complete: {krmi}")
        if not partial.is_file() or not journal.is_file():
            raise FileNotFoundError("Resume requires both KRM-IF .partial and .journal.json checkpoints")
        if not (kasf.is_file() and base.is_file() and metadata_path.is_file()):
            raise FileNotFoundError("Resume requires the original KASF file, Base WAV, and metadata sidecar")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_wav_sha256") != sha256_file(source):
            raise ValueError("Source WAV changed since the KRC checkpoint was created")
        if metadata.get("kasf_sha256") != sha256_file(kasf):
            raise ValueError("KASF file changed since the KRC checkpoint was created")
        track_info = metadata.get("track_map")
        if track_info:
            track_path = Path(track_info.get("path", ""))
            if not track_path.is_file() or track_info.get("sha256") != sha256_file(track_path):
                raise ValueError("Temporal track map is missing or changed since the KRC checkpoint was created")
        base_info = metadata.get("reader_bridge", {}).get("native_base_wav")
        if not isinstance(base_info, dict) or base_info.get("base_wav_sha256") != sha256_file(base):
            raise ValueError("Base WAV is missing or changed since the KRC checkpoint was created")
        spec = _source_spec(source)
        if (base_info.get("channels"), base_info.get("sample_rate_hz"), base_info.get("sample_count"), base_info.get("sample_width_bytes")) != (spec.channels, spec.sample_rate, spec.sample_count, spec.sample_width):
            raise ValueError("Saved Base WAV metadata does not match the Source WAV domain")
        with open(kasf, "rb") as fp:
            header = read_header(fp)
        stats = metadata.get("generator_stats")
        if not isinstance(stats, dict) or header.channels != spec.channels or header.frame_count != stats.get("frame_count"):
            raise ValueError("Saved KASF header or generator statistics failed resume validation")
        gen = {"output": str(kasf), "metadata": str(metadata_path), "base_wav": base_info, **stats}
    else:
        if not force and (partial.exists() or journal.exists()):
            raise FileExistsError("A KRC checkpoint already exists; set resume=True to continue it, or force=True to discard it")
        if krmi.exists() and not force:
            raise FileExistsError(f"KRM-IF output exists: {krmi}")
        if base.exists() and not force:
            raise FileExistsError(f"Base WAV output exists: {base}")
        if force:
            base.unlink(missing_ok=True)
            krmi.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            journal.unlink(missing_ok=True)
        gen = generate_kasf(
            source, kasf, frame_ms=frame_ms, max_components=max_components,
            threshold_db=threshold_db, min_hz=min_hz, edge_pad=edge_pad,
            temporal_tracking=temporal_tracking, temporal_refinement=temporal_refinement,
            tracker_assignment=tracker_assignment, base_wav=base, force=force, binary=binary,
        )
        base_info = gen.get("base_wav")
        if not base_info:
            raise RuntimeError("Native Reader Base WAV was not returned by FastGen")
        metadata_path = Path(gen["metadata"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    provenance = {
        "origin": "experimental_KASF_FastGen_plus_local_Reader_OLA",
        "engine": "KASF Fast Baseline Generator",
        "engine_revision": metadata["generator"]["version"],
        "reader_version": "Rev.0.9.20 KASF05_Reader local OLA equation; native C++ equivalent",
        "source_wav_sha256": metadata["source_wav_sha256"],
        "kasf_sha256": metadata["kasf_sha256"],
        "sample_rate_hz": base_info["sample_rate_hz"],
        "sample_count": base_info["sample_count"],
        "normalization_policy": "none",
        "integer_pcm_quantizer": PCM_QUANTIZER,
        "base_wav_sha256": base_info["base_wav_sha256"],
        "renderer": base_info["renderer"],
        "alignment": "identity after symmetric half-window guard crop; native-rate, same channel order and source sample count",
        "edge_padding_samples_each_side": base_info["edge_padding_samples_each_side"],
        "canonical_kasf_export": False,
        "temporal_tracking_enabled": metadata.get("generator", {}).get("temporal_tracking", {}).get("enabled", False),
        "temporal_tracker_assignment": metadata.get("generator", {}).get("temporal_tracking", {}).get("assignment", "greedy"),
        "temporal_track_map_sha256": (metadata.get("track_map") or {}).get("sha256"),
        "temporal_tracking_payload_modified": metadata.get("generator", {}).get("temporal_tracking", {}).get("experimental_refinement_enabled", False),
    }
    manifest = capture_residual(source, base, krmi, chunk_samples, base_provenance=provenance, resume=resume)
    return {
        "generator": gen,
        "reader_bridge": base_info,
        "krm_if": str(krmi),
        "krm_audio": manifest["audio"],
        "krm_container": manifest["container"],
        "status": "CAPTURED_EXACT_RESIDUAL",
        "important": "This experiment validates the FastGen-to-local-Reader-to-KRC prototype path, not equivalence to the full Rev.0.9.20 optimized encoder or an official KASF PCM export.",
    }


def main() -> None:
    p = argparse.ArgumentParser(prog="krm_fastgen", description="Build and run the native KASF Fast baseline generator")
    sub = p.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="Compile the native C++17 engine")
    b.add_argument("--output")
    b.add_argument("--compiler")
    g = sub.add_parser("generate", help="Generate a KASF v1 file from a PCM WAV")
    g.add_argument("--input", required=True); g.add_argument("--output", required=True)
    g.add_argument("--frame-ms", type=float, default=10.0)
    g.add_argument("--max-components", type=int, default=48)
    g.add_argument("--threshold-db", type=float, default=-58.0)
    g.add_argument("--min-hz", type=float, default=15.0)
    g.add_argument("--no-edge-pad", action="store_true", help="Disable half-window pre/post padding")
    g.add_argument("--no-tracking", action="store_true", help="Disable temporal track-map generation")
    g.add_argument("--experimental-track-refine", action="store_true", help="Experimental; changes frequency/phase payload")
    g.add_argument("--tracker-assignment", choices=("greedy", "hungarian"), default="greedy")
    g.add_argument("--base-wav", help="Also emit native local-Reader Base WAV")
    g.add_argument("--force", action="store_true"); g.add_argument("--binary")
    r = sub.add_parser("bridge", help="Generate KASF, render Base WAV, and capture KRM-IF residual")
    r.add_argument("--source", required=True); r.add_argument("--kasf", required=True)
    r.add_argument("--base", required=True); r.add_argument("--krmi", required=True)
    r.add_argument("--frame-ms", type=float, default=10.0)
    r.add_argument("--max-components", type=int, default=48)
    r.add_argument("--threshold-db", type=float, default=-58.0)
    r.add_argument("--min-hz", type=float, default=15.0)
    r.add_argument("--no-edge-pad", action="store_true", help="Disable half-window pre/post padding")
    r.add_argument("--no-tracking", action="store_true", help="Disable temporal track-map generation")
    r.add_argument("--experimental-track-refine", action="store_true", help="Experimental; changes frequency/phase payload")
    r.add_argument("--tracker-assignment", choices=("greedy", "hungarian"), default="greedy")
    r.add_argument("--chunk-samples", type=int, default=65_536)
    r.add_argument("--resume", action="store_true", help="Resume the KRC partial file without regenerating KASF/Base")
    r.add_argument("--force", action="store_true"); r.add_argument("--binary")
    args = p.parse_args()
    if args.command == "build":
        print(json.dumps({"binary": str(build_native(args.output, args.compiler))}, indent=2))
    elif args.command == "generate":
        print(json.dumps(generate_kasf(args.input, args.output, frame_ms=args.frame_ms,
            max_components=args.max_components, threshold_db=args.threshold_db,
            min_hz=args.min_hz, edge_pad=not args.no_edge_pad,
            temporal_tracking=not args.no_tracking, temporal_refinement=args.experimental_track_refine,
            tracker_assignment=args.tracker_assignment, base_wav=args.base_wav, force=args.force, binary=args.binary), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(generate_and_capture(args.source, args.kasf, args.base, args.krmi,
            frame_ms=args.frame_ms, max_components=args.max_components,
            threshold_db=args.threshold_db, min_hz=args.min_hz,
            edge_pad=not args.no_edge_pad, temporal_tracking=not args.no_tracking,
            temporal_refinement=args.experimental_track_refine, tracker_assignment=args.tracker_assignment,
            chunk_samples=args.chunk_samples, force=args.force, resume=args.resume, binary=args.binary), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
