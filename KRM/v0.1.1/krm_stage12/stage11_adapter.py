"""Adapter from the original KRM Stage11 silence-typing implementation to Stage12.

The adapter calls Stage11's own analyze_signal() routine (not a reimplementation),
then converts its frequency-major arrays into Stage12's (frame, bin) sparse map.
S0 is implicit only because Stage11 classifies every cell in a complete grid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Optional


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _load_stage11_summary(summary_path: Optional[str | Path], channel: int) -> Optional[dict]:
    if summary_path is None:
        return None
    p = Path(summary_path)
    if not p.is_file():
        raise FileNotFoundError(p)
    data = json.loads(p.read_text(encoding="utf-8"))
    channels = data.get("channels", [])
    for item in channels:
        if item.get("channel") == channel:
            return {"root": data, "channel": item, "path": p}
    raise ValueError(f"Stage11 summary has no channel {channel}")


def build_normalized_input(
    npz_path: str | Path,
    channel: int,
    *,
    summary_path: Optional[str | Path] = None,
    input_id: Optional[str] = None,
) -> dict:
    """Run the exact Stage11 implementation and produce compact normalized 1.1 data.

    The normalized map omits S0 cells and declares them as the implicit state of
    a complete grid. S1/S2/S3 records keep the linear power and floor/activity
    measures required by Stage12. The source NPZ is never modified.
    """
    try:
        import numpy as np
        from scipy.ndimage import median_filter
        from krm_stage11.analysis.stage11_silence_typing import (
            FS, NFFT, HOP, EPS, analyze_signal,
        )
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "Stage11 adapter requires NumPy and SciPy; install KRM with the [stage11] extra"
        ) from exc

    source = Path(npz_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if isinstance(channel, bool) or not isinstance(channel, int) or channel < 0:
        raise ValueError("channel must be a non-negative integer")

    with np.load(source, allow_pickle=False) as arrays:
        if "R" not in arrays.files:
            raise ValueError("Stage11 input NPZ does not contain raw residual array 'R'")
        residual = arrays["R"]
        if residual.ndim != 2:
            raise ValueError(f"R must be a 2-D (samples, channels) array; got {residual.shape}")
        if channel >= residual.shape[1]:
            raise ValueError(f"channel {channel} is outside {residual.shape[1]} available channels")
        signal = np.asarray(residual[:, channel], dtype=np.float64)
        sample_count = int(signal.size)

    # This is the Stage11 source function, including its STFT settings, floor
    # estimation, smoothing, and S0-S3 thresholds.
    freqs, times, power, excess_db, typing, regions, stage11_stats = analyze_signal(
        signal, fs=FS, nfft=NFFT, hop=HOP
    )
    if typing.shape != power.shape or typing.shape != excess_db.shape:
        raise AssertionError("Stage11 returned inconsistent time-frequency array shapes")
    if typing.shape != (len(freqs), len(times)):
        raise AssertionError("Stage11 array orientation changed; refusing implicit transpose")

    # Reconstruct the same local floor used by analyze_signal(): temporal median
    # by frequency followed by a 9-bin median filter and EPS clipping.
    floor = np.median(power, axis=1)
    floor = median_filter(floor, size=9, mode="nearest")
    floor = np.maximum(floor, EPS)

    total = int(typing.size)
    class_counts = {f"S{i}": int(np.count_nonzero(typing == i)) for i in range(4)}
    if sum(class_counts.values()) != total:
        raise AssertionError("Stage11 class counts do not cover the full grid")
    if stage11_stats.get("cells") != total:
        raise AssertionError("Stage11 summary cell count mismatch")
    if stage11_stats.get("class_counts") != class_counts:
        raise AssertionError("Stage11 summary class counts mismatch")

    summary = _load_stage11_summary(summary_path, channel)
    if summary:
        original_input_hash = summary["root"].get("input_sha256")
        npz_hash = _sha256_file(source)
        if original_input_hash and original_input_hash != npz_hash:
            raise ValueError("NPZ SHA-256 does not match the Stage11 summary provenance")
        expected = summary["channel"]
        if expected.get("frames") != len(times) or expected.get("frequency_bins") != len(freqs):
            raise ValueError("Stage11 summary grid dimensions do not match reproduced analysis")
        if expected.get("class_counts") != class_counts:
            raise ValueError("Reproduced Stage11 class counts differ from saved Stage11 results")
        if expected.get("candidate_region_count") != len(regions):
            raise ValueError("Reproduced Stage11 candidate-region count differs from saved results")
        if expected.get("candidate_region_total_area_cells") != int(sum(r["area_cells"] for r in regions)):
            raise ValueError("Reproduced Stage11 candidate-region total area differs from saved results")
        if expected.get("regions") != regions:
            raise ValueError("Reproduced Stage11 region records differ from saved region records")

    cells = {}
    # Stage11 arrays are [frequency_bin, frame]; Stage12 cell keys are
    # [frame, frequency_bin]. S0 is represented by the complete-grid default.
    for bin_index, frame_index in np.argwhere(typing != 0):
        state_code = int(typing[bin_index, frame_index])
        state = f"S{state_code}"
        rec = {"state": state, "power": float(power[bin_index, frame_index])}
        if state_code == 1:
            rec["local_floor_power"] = float(floor[bin_index])
        if state_code >= 2:
            rec["delta_db"] = float(excess_db[bin_index, frame_index])
        cells[f"{int(frame_index)},{int(bin_index)}"] = rec

    npz_hash = _sha256_file(source)
    script_path = Path(__file__).resolve().parents[1] / "krm_stage11" / "analysis" / "stage11_silence_typing.py"
    script_hash = _sha256_file(script_path)
    summary_hash = _sha256_file(summary["path"]) if summary else None
    base_manifest = {
        "input_id": input_id or f"stage11-{source.stem}-ch{channel}-{npz_hash[:12]}",
        "sample_rate": int(FS),
        "fft_size": int(NFFT),
        "hop_size": int(HOP),
        "window": "hann",
        "center_padding": "none",
        "frame_timestamp_convention": "center",
        "frequency_bin_convention": "rfft",
        "stage11_version": "KRM-Stage11-SilenceBasedTyping-2026-11-15",
        "channel_id": int(channel),
        "resolution_id": "stft-hann-2048-512-boundary-none",
        "frame_count": int(len(times)),
        "bin_count": int(len(freqs)),
        "grid_complete": True,
        "implicit_cell_state": "S0",
        "cell_encoding": "sparse-complete-grid-implicit-state-1.0",
        "source_sample_count": sample_count,
        "source_arrays_sha256": npz_hash,
        "stage11_source_sha256": script_hash,
        "stage11_summary_sha256": summary_hash,
        "stage11_typing_thresholds_db": {"S0_upper_exclusive": 6.0, "S1_lower": 6.0, "S1_upper_exclusive": 12.0, "S2_lower": 12.0, "S2_upper_exclusive": 24.0, "S3_lower": 24.0},
        "stage11_floor_method": "per-frequency temporal median; median_filter size=9 across frequency bins; EPS=1e-30",
        "stage11_region_method": "3x3 binary closing on S2/S3; 8-neighbour components; retain area>=4 cells and duration>=2 frames",
        "frame_time_start_s": float(times[0]) if len(times) else None,
        "frame_time_end_s": float(times[-1]) if len(times) else None,
        "frequency_min_hz": float(freqs[0]) if len(freqs) else None,
        "frequency_max_hz": float(freqs[-1]) if len(freqs) else None,
        "data_provenance": (
            summary["root"].get("data_provenance") if summary else
            "Source provenance not supplied; this adapter only certifies the supplied NPZ bytes and Stage11 computation."
        ),
    }

    return {
        "schema_version": "krm-stage11-normalized-1.1",
        "input_manifest": base_manifest,
        "cells": cells,
        "stage11_reproduction": {
            "frames": int(len(times)),
            "frequency_bins": int(len(freqs)),
            "cells_total": total,
            "class_counts": class_counts,
            "class_percent": {k: (100.0 * v / total if total else 0.0) for k, v in class_counts.items()},
            "candidate_region_count": int(len(regions)),
            "candidate_region_total_area_cells": int(sum(r["area_cells"] for r in regions)),
            "median_floor_db_power": float(np.median(10 * np.log10(floor + EPS))),
            "sparse_records": len(cells),
            "implicit_s0_cells": class_counts["S0"],
            "parity_with_saved_stage11_summary": bool(summary is not None),
            "candidate_region_records_match": bool(summary is not None),
        },
    }


def write_normalized_input(data: dict, output_path: str | Path) -> Path:
    from krm_stage12.core import validate_input
    validate_input(data)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="KRM Stage11 -> Stage12 adapter")
    parser.add_argument("input_npz", help="Stage11 source NPZ containing R")
    parser.add_argument("--channel", type=int, required=True, help="zero-based channel index")
    parser.add_argument("--summary", help="original Stage11 stage11_summary.json for parity checks")
    parser.add_argument("--output", required=True, help="normalized Stage12 JSON output")
    parser.add_argument("--run-stage12", action="store_true", help="run Stage12 after normalization")
    parser.add_argument("--stage12-output", default="KRM_STAGE12_STAGE11_RUN", help="Stage12 output bundle directory")
    parser.add_argument("--disable-s1-bridge", action="store_true", help="disable Stage12-B4 S1 bridging for controlled comparison")
    args = parser.parse_args(argv)

    data = build_normalized_input(args.input_npz, args.channel, summary_path=args.summary)
    out = write_normalized_input(data, args.output)
    print(json.dumps(data["stage11_reproduction"], ensure_ascii=False, indent=2))
    print(f"normalized_input={out}")
    if args.run_stage12:
        from krm_stage12.core import Config, run_stage12, write_bundle
        cfg = Config(s1_bridge_enabled=not args.disable_s1_bridge)
        result = run_stage12(data, cfg)
        write_bundle(result, args.stage12_output)
        print(json.dumps(result["validation"], ensure_ascii=False, indent=2))
        print(f"stage12_output={Path(args.stage12_output).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
