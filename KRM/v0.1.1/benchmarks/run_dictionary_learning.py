"""Train/validation experiment for time-domain convolutional dictionary learning.

The file is intentionally independent of KASF and makes no frequency-domain
transforms. Stereo channels are treated as separate training examples sharing
one dictionary; no inter-channel coupling is imposed in this experiment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import wave

import numpy as np

from krm_td_csc.dictionary import initialize_dictionary_from_signal
from krm_td_csc.learning import learn_convolutional_dictionary
from krm_td_csc.metrics import relative_l2_error, snr_db
from krm_td_csc.operators import adjoint
from krm_td_csc.solver import solve_cbpdn_fista


def read_pcm_wav(path: Path) -> tuple[np.ndarray, dict]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        width = wf.getsampwidth()
        frames = wf.getnframes()
        raw = wf.readframes(frames)
    if channels < 1 or rate < 1:
        raise ValueError("invalid WAV metadata")
    if width == 1:
        values = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - 128.0
    elif width == 2:
        values = np.frombuffer(raw, dtype="<i2").astype(np.float64)
    elif width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        integer = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        integer = np.where(integer & 0x800000, integer - 0x1000000, integer)
        values = integer.astype(np.float64)
    elif width == 4:
        values = np.frombuffer(raw, dtype="<i4").astype(np.float64)
    else:
        raise ValueError(f"unsupported PCM width: {width}")
    if values.size != frames * channels:
        raise ValueError("WAV payload length is inconsistent with metadata")
    planar = values.reshape(-1, channels).T.copy()
    peak = float(np.max(np.abs(planar), initial=0.0))
    if peak > 0:
        planar *= 0.75 / peak
    metadata = {
        "filename": path.name,
        "channels": int(channels),
        "sample_rate_hz": int(rate),
        "sample_width_bytes": int(width),
        "frames": int(frames),
        "duration_seconds": frames / rate,
        "normalisation_peak_before": peak,
        "normalisation_peak_after": float(np.max(np.abs(planar), initial=0.0)),
    }
    return planar, metadata


def make_splits(
    planar: np.ndarray,
    segment_samples: int,
    train_count: int,
    validation_count: int,
    seed: int,
) -> tuple[list[np.ndarray], list[np.ndarray], list[int], list[int]]:
    total = train_count + validation_count
    n = planar.shape[1]
    if segment_samples < 32 or total < 4 or n < segment_samples * 2:
        raise ValueError("need segment_samples >= 32, at least 4 segments, and a longer WAV")
    starts = np.linspace(0, n - segment_samples, total, dtype=np.int64)
    # Randomly assign time-distributed, non-overlapping candidate windows to
    # train/validation while preserving deterministic reproducibility.
    order = np.random.default_rng(seed).permutation(total)
    train_indices = np.sort(order[:train_count])
    validation_indices = np.sort(order[train_count:])
    train = [planar[:, s:s + segment_samples].copy() for s in starts[train_indices]]
    validation = [planar[:, s:s + segment_samples].copy() for s in starts[validation_indices]]
    # Each channel/window is an independent example sharing one waveform dictionary.
    train_examples = [window[ch].copy() for window in train for ch in range(planar.shape[0])]
    validation_examples = [window[ch].copy() for window in validation for ch in range(planar.shape[0])]
    return train_examples, validation_examples, starts[train_indices].tolist(), starts[validation_indices].tolist()


def encode_all(signals: list[np.ndarray], atoms: list[np.ndarray], lam: float, iterations: int, seed: int) -> list:
    results = []
    for index, signal in enumerate(signals):
        results.append(solve_cbpdn_fista(
            signal, atoms, lam=lam, max_iterations=iterations,
            tolerance=1e-5, power_iterations=18, seed=seed + index,
        ))
    return results


def aggregate_metrics(signals: list[np.ndarray], results: list) -> dict:
    source = np.concatenate(signals)
    estimate = np.concatenate([r.reconstruction for r in results])
    return {
        "aggregate_snr_db": snr_db(source, estimate),
        "relative_l2_error": relative_l2_error(source, estimate),
        "mean_segment_snr_db": float(np.mean([snr_db(x, r.reconstruction) for x, r in zip(signals, results)])),
        "coded_examples": len(signals),
        "coding_converged_count": int(sum(bool(r.converged) for r in results)),
        "coding_iterations_total": int(sum(int(r.iterations) for r in results)),
        "mean_optimality_residual": float(np.mean([r.optimality_residual for r in results])),
        "max_optimality_residual": float(np.max([r.optimality_residual for r in results])),
    }


def atom_statistics(initial: list[np.ndarray], learned: list[np.ndarray]) -> dict:
    cosines = [abs(float(np.dot(a, b))) for a, b in zip(initial, learned)]
    matrix = np.stack(learned)
    gram = np.abs(matrix @ matrix.T)
    np.fill_diagonal(gram, 0.0)
    max_coherence = float(np.max(gram, initial=0.0))
    mean_coherence = float(np.sum(gram) / max(1, len(learned) * (len(learned) - 1)))
    return {
        "mean_absolute_initial_to_learned_cosine_same_index": float(np.mean(cosines)),
        "min_absolute_initial_to_learned_cosine_same_index": float(np.min(cosines)),
        "max_pairwise_absolute_coherence_learned_dictionary": max_coherence,
        "mean_pairwise_absolute_coherence_learned_dictionary": mean_coherence,
    }


def run_one(
    path: Path,
    *,
    segment_samples: int,
    train_count: int,
    validation_count: int,
    atom_length: int,
    atom_count: int,
    outer_iterations: int,
    coding_iterations: int,
    seed: int,
) -> dict:
    planar, metadata = read_pcm_wav(path)
    train, validation, train_starts, validation_starts = make_splits(
        planar, segment_samples, train_count, validation_count, seed,
    )
    # Place silence between training segments so the initial patch selector
    # never constructs an atom across a segment boundary.
    gap = np.zeros(atom_length, dtype=np.float64)
    joined = np.concatenate([
        np.concatenate([signal, gap]) for signal in train
    ])
    initial_atoms = initialize_dictionary_from_signal(
        joined, scales=(atom_length,), atoms_per_scale=atom_count,
        seed=seed, candidate_limit=512, min_rms=1e-8,
    )
    max_correlation = max(
        float(np.max(np.abs(adjoint(signal, initial_atoms)), initial=0.0))
        for signal in train
    )
    lam = 0.01 * max_correlation

    baseline_start = time.perf_counter()
    baseline_train = encode_all(train, initial_atoms, lam, coding_iterations, seed + 100)
    baseline_validation = encode_all(validation, initial_atoms, lam, coding_iterations, seed + 200)
    baseline_seconds = time.perf_counter() - baseline_start

    learning_start = time.perf_counter()
    learned = learn_convolutional_dictionary(
        train, initial_atoms, lam=lam,
        outer_iterations=outer_iterations,
        coding_iterations=coding_iterations,
        coding_tolerance=1e-5,
        initial_dictionary_step=100.0,
        max_dictionary_backtracking=35,
        power_iterations=18,
        seed=seed + 300,
    )
    learning_seconds = time.perf_counter() - learning_start

    learned_train = encode_all(train, learned.atoms, lam, coding_iterations, seed + 400)
    learned_validation = encode_all(validation, learned.atoms, lam, coding_iterations, seed + 500)

    return {
        "audio": metadata,
        "split": {
            "segment_samples": segment_samples,
            "train_window_starts": train_starts,
            "validation_window_starts": validation_starts,
            "train_examples_including_channels": len(train),
            "validation_examples_including_channels": len(validation),
            "channel_policy": "channels treated as independent examples with one shared dictionary; no joint channel model",
        },
        "model": {
            "atom_length": atom_length,
            "atom_count": len(initial_atoms),
            "filter_parameter_count": int(sum(len(a) for a in initial_atoms)),
            "lambda": lam,
            "solver": "direct-time-domain monotone FISTA + projected unit-sphere dictionary gradient + Armijo backtracking",
        },
        "initial_dictionary": {
            "train": aggregate_metrics(train, baseline_train),
            "validation": aggregate_metrics(validation, baseline_validation),
        },
        "learned_dictionary": {
            "train": aggregate_metrics(train, learned_train),
            "validation": aggregate_metrics(validation, learned_validation),
            "objective_history": learned.objective_history,
            "smooth_loss_history": learned.smooth_loss_history,
            "dictionary_step_history": learned.dictionary_step_history,
            "dictionary_gradient_norm_history": learned.dictionary_gradient_norm_history,
            "coding_converged_count": int(sum(learned.coding_converged)),
            "coding_solve_count": len(learned.coding_converged),
            "mean_training_optimality_residual_over_all_outer_solves": float(np.mean(learned.coding_optimality_residuals)),
            "max_training_optimality_residual_over_all_outer_solves": float(np.max(learned.coding_optimality_residuals)),
            "inactive_atoms": learned.inactive_atoms,
            "atom_statistics": atom_statistics(initial_atoms, learned.atoms),
        },
        "timing_seconds": {
            "baseline_encode_train_and_validation": baseline_seconds,
            "alternating_dictionary_learning_only": learning_seconds,
        },
        "caveats": [
            "This is a small, in-sample dictionary-training experiment with a held-out time-window validation split, not a broad generalisation claim.",
            "The validation windows are not used for dictionary initialisation or learning.",
            "Atom identity and sign are permutation/sign ambiguous; same-index cosine is diagnostic only.",
            "No FFT/STFT/DCT or frequency-domain representation is used.",
            "The dictionary is shared across channels, but activations are independent; inter-channel coupling is not implemented.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, action="append", required=True, help="PCM WAV; repeat for multiple tests")
    parser.add_argument("--segment-samples", type=int, default=512)
    parser.add_argument("--train-count", type=int, default=6, help="time windows, before channel expansion")
    parser.add_argument("--validation-count", type=int, default=4, help="held-out time windows, before channel expansion")
    parser.add_argument("--atom-length", type=int, default=24)
    parser.add_argument("--atoms", type=int, default=6)
    parser.add_argument("--outer-iterations", type=int, default=8)
    parser.add_argument("--coding-iterations", type=int, default=80)
    parser.add_argument("--seed", type=int, default=37)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/dictionary-learning-draft-0.8.json"))
    args = parser.parse_args()

    all_results = []
    for path in args.wav:
        all_results.append(run_one(
            path,
            segment_samples=args.segment_samples,
            train_count=args.train_count,
            validation_count=args.validation_count,
            atom_length=args.atom_length,
            atom_count=args.atoms,
            outer_iterations=args.outer_iterations,
            coding_iterations=args.coding_iterations,
            seed=args.seed,
        ))
    report = {
        "benchmark_version": "KRM-TD-CDL-Benchmark-0.1",
        "algorithm": "Alternating Convolutional Dictionary Learning; direct time-domain operators",
        "results": all_results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    print(f"\nWROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
