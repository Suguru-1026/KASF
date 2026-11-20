#!/usr/bin/env python3
"""Compare Greedy and Hungarian KASF FastGen track association on PCM WAV input."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from krm_proto.fastgen import generate_kasf, sha256_file  # noqa: E402
from krm_proto.pcm import decode_interleaved, read_wav_spec  # noqa: E402


def source_base_snr_db(source: Path, base: Path) -> float:
    signal_energy = 0
    error_energy = 0
    with wave.open(str(source), "rb") as src, wave.open(str(base), "rb") as rendered:
        src_spec = read_wav_spec(src)
        base_spec = read_wav_spec(rendered)
        if src_spec != base_spec:
            raise ValueError("Base WAV parameters do not match Source WAV")
        while True:
            source_raw = src.readframes(65_536)
            base_raw = rendered.readframes(65_536)
            if not source_raw and not base_raw:
                break
            if len(source_raw) != len(base_raw):
                raise ValueError("Source and Base PCM lengths differ")
            source_channels = decode_interleaved(source_raw, src_spec)
            base_channels = decode_interleaved(base_raw, base_spec)
            for ch in range(src_spec.channels):
                for x, b in zip(source_channels[ch], base_channels[ch]):
                    signal_energy += x * x
                    error_energy += (x - b) * (x - b)
    if error_energy == 0:
        return float("inf")
    if signal_energy == 0:
        return float("-inf")
    return 10.0 * math.log10(signal_energy / error_energy)


def track_lifetimes(track_map: Path, channels: int) -> dict:
    by_channel: list[dict[int, int]] = [dict() for _ in range(channels)]
    row_count = 0
    with track_map.open("r", encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            row = json.loads(line)
            row_count += 1
            ch = int(row["channel"])
            if ch < 0 or ch >= channels:
                raise ValueError(f"Invalid track-map channel: {ch}")
            for raw_id in row["track_ids"]:
                track_id = int(raw_id)
                if track_id:
                    by_channel[ch][track_id] = by_channel[ch].get(track_id, 0) + 1
    result = {}
    for ch, tracks in enumerate(by_channel):
        lengths = sorted(tracks.values())
        result[str(ch)] = {
            "unique_track_ids": len(lengths),
            "median_lifetime_frames": statistics.median(lengths) if lengths else 0,
            "p90_lifetime_frames": lengths[min(len(lengths) - 1, math.floor(0.9 * len(lengths)))] if lengths else 0,
            "max_lifetime_frames": max(lengths, default=0),
            "tracks_at_least_10_frames": sum(n >= 10 for n in lengths),
            "tracks_at_least_50_frames": sum(n >= 50 for n in lengths),
            "tracks_at_least_100_frames": sum(n >= 100 for n in lengths),
        }
    return {"rows": row_count, "channels": result}



def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_wav", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("tracker-assignment-results"))
    parser.add_argument("--frame-ms", type=float, default=10.0)
    parser.add_argument("--max-components", type=int, default=32)
    parser.add_argument("--threshold-db", type=float, default=-58.0)
    parser.add_argument("--min-hz", type=float, default=15.0)
    args = parser.parse_args()

    source = args.source_wav.expanduser().resolve()
    if not source.is_file():
        parser.error(f"Source WAV does not exist: {source}")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    results = {}

    for mode in ("greedy", "hungarian"):
        stem = source.stem
        kasf = output_dir / f"{stem}.{mode}.kasf"
        base = output_dir / f"{stem}.{mode}.base.wav"
        generation = generate_kasf(
            source, kasf,
            frame_ms=args.frame_ms,
            max_components=args.max_components,
            threshold_db=args.threshold_db,
            min_hz=args.min_hz,
            edge_pad=True,
            temporal_tracking=True,
            tracker_assignment=mode,
            base_wav=base,
            force=True,
        )
        metadata = json.loads(Path(generation["metadata"]).read_text(encoding="utf-8"))
        track_info = metadata["track_map"]
        track_summary = track_lifetimes(Path(track_info["path"]), generation["channels"])
        expected_rows = generation["frame_count"] * generation["channels"]
        if track_summary["rows"] != expected_rows:
            raise ValueError(f"Track-map rows {track_summary['rows']} do not match expected {expected_rows}")
        snr = source_base_snr_db(source, base)
        if not math.isfinite(snr):
            snr = "+inf" if snr > 0 else "-inf"
        results[mode] = {
            "generator_elapsed_seconds": generation["elapsed_seconds"],
            "frame_count": generation["frame_count"],
            "component_count": generation["components"],
            "tracks_created": generation["temporal_tracks_created"],
            "matched_components": generation["temporal_matches"],
            "source_base_snr_db": snr,
            "kasf_sha256": sha256_file(kasf),
            "base_wav_sha256": sha256_file(base),
            "track_map_sha256": track_info["sha256"],
            "track_lifetimes": track_summary,
            "outputs": {"kasf": str(kasf), "base_wav": str(base), "track_map": track_info["path"]},
        }

    results["invariants"] = {
        "kasf_byte_identical": results["greedy"]["kasf_sha256"] == results["hungarian"]["kasf_sha256"],
        "base_wav_byte_identical": results["greedy"]["base_wav_sha256"] == results["hungarian"]["base_wav_sha256"],
        "track_map_sha256_differs": results["greedy"]["track_map_sha256"] != results["hungarian"]["track_map_sha256"],
    }
    rendered = json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False)
    report_path = output_dir / f"{source.stem}.tracker-assignment-report.json"
    report_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
