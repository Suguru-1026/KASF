"""Reproduce one-window FISTA proximal-gradient/KKT convergence diagnostics."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from run_dictionary_learning import read_pcm_wav
from krm_td_csc.dictionary import initialize_dictionary_from_signal
from krm_td_csc.metrics import relative_l2_error, snr_db
from krm_td_csc.operators import adjoint
from krm_td_csc.solver import solve_cbpdn_fista


def run(path: Path, channel: int, start_sample: int, length: int,
        atom_length: int, atom_count: int, seed: int, caps: list[int]) -> dict:
    planar, metadata = read_pcm_wav(path)
    if channel < 0 or channel >= planar.shape[0]:
        raise ValueError(f"channel must be in [0, {planar.shape[0] - 1}]")
    if start_sample < 0 or start_sample + length > planar.shape[1]:
        raise ValueError("selected window is outside the WAV")
    if planar.shape[0] > 1:
        patch_parts = [planar[ch, :max(length, atom_length * 4)] for ch in range(planar.shape[0])]
        joined = np.concatenate([
            np.concatenate([part, np.zeros(atom_length)]) for part in patch_parts
        ])
    else:
        joined = planar[0, :max(length, atom_length * 4)]
    atoms = initialize_dictionary_from_signal(
        joined, scales=(atom_length,), atoms_per_scale=atom_count,
        seed=seed, candidate_limit=512, min_rms=1e-8,
    )
    signal = planar[channel, start_sample:start_sample + length].copy()
    lambda_value = 0.01 * max(
        float(np.max(np.abs(adjoint(signal, atoms)), initial=0.0)), 1e-12,
    )
    trials = []
    for cap in caps:
        started = time.perf_counter()
        result = solve_cbpdn_fista(
            signal, atoms, lam=lambda_value, max_iterations=cap,
            tolerance=1e-5, power_iterations=18, seed=seed + 99,
        )
        trials.append({
            "iteration_cap": cap,
            "iterations_used": result.iterations,
            "converged": result.converged,
            "optimality_residual": result.optimality_residual,
            "final_objective": result.objective_history[-1],
            "snr_db": snr_db(signal, result.reconstruction),
            "relative_l2_error": relative_l2_error(signal, result.reconstruction),
            "elapsed_seconds": time.perf_counter() - started,
        })
    return {
        "audio": metadata,
        "selected_window": {
            "channel_index": channel,
            "start_sample": start_sample,
            "sample_count": length,
        },
        "dictionary": {
            "atom_length": atom_length,
            "atom_count": atom_count,
            "seed": seed,
        },
        "lambda": lambda_value,
        "convergence_definition": "converged requires both a small coefficient step and a small proximal-gradient mapping norm",
        "trials": trials,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--start-sample", type=int, default=166336)
    parser.add_argument("--length", type=int, default=512)
    parser.add_argument("--atom-length", type=int, default=24)
    parser.add_argument("--atoms", type=int, default=6)
    parser.add_argument("--seed", type=int, default=37)
    parser.add_argument("--caps", type=int, nargs="+", default=[80, 200, 500])
    parser.add_argument("--output", type=Path, default=Path("benchmarks/fista-kkt-diagnostic.json"))
    args = parser.parse_args()
    report = run(args.wav, args.channel, args.start_sample, args.length,
                 args.atom_length, args.atoms, args.seed, args.caps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"\nWROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
