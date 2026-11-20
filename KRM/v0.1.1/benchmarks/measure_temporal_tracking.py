#!/usr/bin/env python3
"""Reproducible synthetic check for FastGen's metadata-only temporal tracker."""
from __future__ import annotations

import json
import math
import struct
import tempfile
import time
import wave
from pathlib import Path

from krm_proto.fastgen import build_native, generate_kasf
from krm_proto.kasf_reader import read_header, _iter_frames


def write_source(path: Path, rate: int = 16_000, seconds: float = 2.0) -> None:
    count = int(rate * seconds)
    phases = [0.0, 0.0]
    with wave.open(str(path), "wb") as dst:
        dst.setnchannels(2)
        dst.setsampwidth(2)
        dst.setframerate(rate)
        raw = bytearray()
        for i in range(count):
            t = i / rate
            f_left = 440.0 + 4.0 * math.sin(2.0 * math.pi * 0.6 * t)
            f_right = 523.25 + 3.0 * math.sin(2.0 * math.pi * 0.45 * t)
            phases[0] += 2.0 * math.pi * f_left / rate
            phases[1] += 2.0 * math.pi * f_right / rate
            left = 0.28 * math.sin(phases[0] + 0.2) + 0.10 * math.sin(2.0 * math.pi * 997.0 * t + 0.7)
            right = 0.25 * math.sin(phases[1] - 0.3) + 0.09 * math.sin(2.0 * math.pi * 1319.0 * t + 0.4)
            raw.extend(struct.pack("<hh", round(left * 32768), round(right * 32768)))
        dst.writeframes(raw)


def read_pcm(path: Path) -> tuple[bytes, tuple[int, int, int, int]]:
    with wave.open(str(path), "rb") as src:
        params = (src.getnchannels(), src.getsampwidth(), src.getframerate(), src.getnframes())
        return src.readframes(src.getnframes()), params


def snr_db(source: bytes, base: bytes, width: int = 2) -> float:
    scale = 1 << (width * 8 - 1)
    samples = len(source) // width
    signal = 0
    error = 0
    for i in range(samples):
        a = int.from_bytes(source[i * width:(i + 1) * width], "little", signed=True)
        b = int.from_bytes(base[i * width:(i + 1) * width], "little", signed=True)
        signal += a * a
        error += (a - b) * (a - b)
    if error == 0:
        return float("inf")
    return 10.0 * math.log10(signal / error)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="krm-track-bench-") as td:
        root = Path(td)
        source = root / "source.wav"
        write_source(source)
        binary = build_native(root / "kasf_fastgen")
        runs = {}
        representative_paths = {}
        for enabled in (False, True):
            label = "tracking" if enabled else "no_tracking"
            elapsed_runs = []
            for repeat in range(3):
                kasf = root / f"{label}-{repeat}.kasf"
                base = root / f"{label}-{repeat}.wav"
                started = time.perf_counter()
                result = generate_kasf(
                    source, kasf, frame_ms=50.0, max_components=4,
                    threshold_db=-58.0, min_hz=20.0, edge_pad=True,
                    temporal_tracking=enabled, base_wav=base, binary=binary,
                )
                elapsed_runs.append(time.perf_counter() - started)
                if repeat == 0:
                    raw, params = read_pcm(base)
                    runs[label] = {
                        "base_pcm_sha256": result["base_wav"]["base_wav_sha256"],
                        "base_pcm_bytes": len(raw),
                        "base_params": params,
                        "snr_db": snr_db(read_pcm(source)[0], raw),
                        "generator_frame_count": result["frame_count"],
                        "component_count": result["components"],
                    }
                    representative_paths[label] = {"kasf": kasf, "base": base}
                    if enabled:
                        track_meta = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
                        track_info = track_meta["track_map"]
                        rows = [json.loads(line) for line in Path(track_info["path"]).read_text(encoding="utf-8").splitlines()]
                        unique_by_channel = {}
                        with Path(kasf).open("rb") as fp:
                            header = read_header(fp)
                            decoded_frames = list(_iter_frames(fp, header))
                        track_observations = {}
                        for row in rows:
                            frame_no = row["frame"]
                            channel = row["channel"]
                            components = decoded_frames[frame_no][channel]
                            if len(components) != len(row["track_ids"]):
                                raise SystemExit("FAIL: track IDs are not aligned with KASF component order")
                            for track_id, component in zip(row["track_ids"], components):
                                track_observations.setdefault((channel, track_id), []).append(component)
                        persistent_by_channel = {}
                        for ch in (0, 1):
                            ids = {tid for row in rows if row["channel"] == ch for tid in row["track_ids"]}
                            unique_by_channel[str(ch)] = len(ids)
                            persistent_by_channel[str(ch)] = sum(
                                1 for (channel, _tid), observations in track_observations.items()
                                if channel == ch and len(observations) >= result["frame_count"] * 0.5
                                and max(item[1] for item in observations) >= 0.04
                            )
                        runs[label]["track_map"] = {
                            "rows": len(rows),
                            "expected_rows": result["frame_count"] * 2,
                            "sha256": track_info["sha256"],
                            "unique_track_ids_by_channel": unique_by_channel,
                            "persistent_tracks_by_channel": persistent_by_channel,
                        }
            elapsed_runs.sort()
            runs[label]["elapsed_median_seconds"] = elapsed_runs[1]
            runs[label]["elapsed_runs_seconds"] = elapsed_runs

        tracking_kasf = representative_paths["tracking"]["kasf"].read_bytes()
        no_tracking_kasf = representative_paths["no_tracking"]["kasf"].read_bytes()
        tracking_base = read_pcm(representative_paths["tracking"]["base"])[0]
        no_tracking_base = read_pcm(representative_paths["no_tracking"]["base"])[0]
        track_meta = runs["tracking"]["track_map"]
        report = {
            "test": "metadata-only temporal tracker",
            "source": {"sample_rate_hz": 16_000, "channels": 2, "seconds": 2.0, "sample_width_bytes": 2},
            "tracking_enabled": runs["tracking"],
            "tracking_disabled": runs["no_tracking"],
            "invariants": {
                "kasf_files_byte_identical": tracking_kasf == no_tracking_kasf,
                "base_pcm_byte_identical": tracking_base == no_tracking_base,
                "track_map_rows_valid": track_meta["rows"] == track_meta["expected_rows"],
            },
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["invariants"]["kasf_files_byte_identical"]:
            raise SystemExit("FAIL: tracking changed KASF output")
        if not report["invariants"]["base_pcm_byte_identical"]:
            raise SystemExit("FAIL: tracking changed Base PCM")
        if not report["invariants"]["track_map_rows_valid"]:
            raise SystemExit("FAIL: track map row count mismatch")


if __name__ == "__main__":
    main()
