#!/usr/bin/env python3
"""Reproducible direct-time-domain multi-scale CSC experiments.

Examples:
  python benchmarks/run_research.py
  python benchmarks/run_research.py --wav /path/to/audio.wav --samples 2048
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import wave
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from krm_td_csc.dictionary import initialize_dictionary_from_signal
from krm_td_csc.operators import adjoint, forward
from krm_td_csc.solver import solve_cbpdn_fista
from krm_td_csc.admm import solve_cbpdn_admm
from krm_td_csc.metrics import snr_db, relative_l2_error


def make_atom(rng: np.random.Generator, length: int, kind: int) -> np.ndarray:
    t = np.linspace(0.0, 1.0, length, endpoint=False)
    if kind % 4 == 0:
        d = rng.normal(size=length) * np.exp(-5.0 * t)
    elif kind % 4 == 1:
        d = np.zeros(length)
        d[0] = 1.0
        if length > 4:
            d[1:4] = rng.normal(0, 0.15, 3)
    elif kind % 4 == 2:
        noise = rng.normal(size=length)
        d = np.convolve(noise, np.ones(5) / 5.0, mode="same") * np.exp(-2.0 * t)
    else:
        d = np.sin(np.cumsum(rng.uniform(0.05, 0.9, size=length))) * np.exp(-1.5 * t)
    d = np.asarray(d, dtype=np.float64)
    d /= max(float(np.linalg.norm(d)), 1e-15)
    return d


def synthetic_case(seed: int = 20261114, n: int = 512):
    rng = np.random.default_rng(seed)
    atoms = [make_atom(rng, length, i) for i, length in enumerate((12, 24, 48, 24))]
    maps = [np.zeros(n + a.size - 1, dtype=np.float64) for a in atoms]
    starts = [4, 33, 100, 184, 276, 402, n - 2]
    for k, a in enumerate(maps):
        for j, start in enumerate(starts[k:k + 4]):
            # map index = absolute start + full-overlap left offset
            a[start + atoms[k].size - 1] = (0.35 + 0.12 * j) * (-1.0 if (j + k) % 2 else 1.0)
    x = forward(maps, atoms, n)
    return x, atoms, maps


def read_wav_mono(path: Path, max_samples: int) -> tuple[np.ndarray, dict]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        width = wf.getsampwidth()
        frames = min(wf.getnframes(), max_samples)
        raw = wf.readframes(frames)
    frame_bytes = channels * width
    if len(raw) % frame_bytes:
        raise ValueError("WAV payload is not frame aligned")
    if width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float64)
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        vals = b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16)
        vals = np.where(vals & 0x800000, vals - 0x1000000, vals)
        data = vals.astype(np.float64)
    else:
        raise ValueError(f"unsupported PCM width: {width}")
    data = data.reshape(-1, channels).mean(axis=1)
    peak = float(np.max(np.abs(data), initial=0.0))
    if peak > 0:
        data = 0.8 * data / peak
    return data, {"channels": channels, "sample_rate_hz": rate, "sample_width_bytes": width, "samples_used": len(data), "peak_before_normalization": peak}


def run_synthetic() -> dict:
    x, atoms, true_maps = synthetic_case()
    lam = 0.002
    fista = solve_cbpdn_fista(x, atoms, lam=lam, max_iterations=1200, tolerance=1e-6, power_iterations=50)
    admm = solve_cbpdn_admm(
        x, atoms, lam=lam, rho=0.1, max_iterations=500,
        cg_tolerance=1e-6, cg_max_iterations=100,
    )
    return {
        "signal_samples": int(x.size),
        "atom_lengths": [int(a.size) for a in atoms],
        "known_sparse_events": int(sum(np.count_nonzero(a) for a in true_maps)),
        "lambda": lam,
        "fista": {
            "iterations": fista.iterations,
            "converged": fista.converged,
            "elapsed_seconds": fista.elapsed_seconds,
            "snr_db": snr_db(x, fista.reconstruction),
            "relative_l2_error": relative_l2_error(x, fista.reconstruction),
            "nonzero_coefficients": fista.sparsity_nonzero,
            "objective_first": fista.objective_history[0],
            "objective_last": fista.objective_history[-1],
        },
        "admm_direct_time_domain": {
            "iterations": admm.iterations,
            "converged": admm.converged,
            "elapsed_seconds": admm.elapsed_seconds,
            "total_cg_iterations": admm.total_cg_iterations,
            "snr_db": snr_db(x, admm.reconstruction),
            "relative_l2_error": relative_l2_error(x, admm.reconstruction),
            "objective_first": admm.objective_history[0],
            "objective_last": admm.objective_history[-1],
            "rho_final": admm.rho_history[-1],
        },
    }


def run_audio(path: Path, samples: int) -> dict:
    x, meta = read_wav_mono(path, samples)
    if x.size < 96:
        raise ValueError("need at least 96 samples for the selected multi-scale benchmark")
    # Self-initialisation is deliberately disclosed: this is an in-sample
    # representation experiment, not held-out generalisation evaluation.
    max_scale = min(64, max(16, (x.size - 1) // 2))
    scales = tuple(s for s in (16, 32, 64) if s <= max_scale and s < x.size)
    multi = initialize_dictionary_from_signal(x, scales=scales, atoms_per_scale=2, seed=17, candidate_limit=256)
    single_scale = 32 if 32 < x.size else max(2, x.size // 4)
    # Match the total number of learned filter coefficients approximately.
    total_filter_parameters = sum(int(d.size) for d in multi)
    single_atom_count = max(1, int(round(total_filter_parameters / single_scale)))
    single = initialize_dictionary_from_signal(x, scales=(single_scale,), atoms_per_scale=single_atom_count, seed=17, candidate_limit=256)

    result = {"path_name": path.name, "audio": meta, "method": "in-sample waveform-patch dictionary initialisation; no FFT/STFT used", "results": {}}
    for name, dictionary in (("multi_scale", multi), ("single_scale", single)):
        correlations = adjoint(x, dictionary)
        lam = 0.01 * max(float(np.max(np.abs(g), initial=0.0)) for g in correlations)
        solved = solve_cbpdn_fista(
            x, dictionary, lam=lam, max_iterations=300,
            tolerance=1e-5, power_iterations=40,
        )
        result["results"][name] = {
            "atom_lengths": [int(d.size) for d in dictionary],
            "atom_count": len(dictionary),
            "filter_parameter_count": int(sum(d.size for d in dictionary)),
            "lambda": lam,
            "iterations": solved.iterations,
            "converged": solved.converged,
            "elapsed_seconds": solved.elapsed_seconds,
            "snr_db": snr_db(x, solved.reconstruction),
            "relative_l2_error": relative_l2_error(x, solved.reconstruction),
            "nonzero_coefficients": solved.sparsity_nonzero,
            "coefficient_count": solved.sparsity_total,
            "objective_first": solved.objective_history[0],
            "objective_last": solved.objective_history[-1],
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", type=Path, action="append", dest="wavs", help="PCM WAV to benchmark; may be repeated")
    parser.add_argument("--samples", type=int, default=2048)
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results-draft-0.7.json")
    args = parser.parse_args()

    result = {"benchmark_version": "KRM-TD-CSC-Benchmark-0.1", "synthetic": run_synthetic()}
    if args.wavs:
        result["real_audio"] = [run_audio(path, args.samples) for path in args.wavs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nWROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
