"""Deterministic, multi-scale waveform-atom initialisation."""
from __future__ import annotations

from typing import Sequence
import numpy as np


def _normalise_patch(patch: np.ndarray, remove_mean: bool) -> np.ndarray | None:
    p = np.asarray(patch, dtype=np.float64).copy()
    if remove_mean:
        p -= np.mean(p)
    norm = float(np.linalg.norm(p))
    if not np.isfinite(norm) or norm < 1e-12:
        return None
    p /= norm
    # Sign canonicalisation removes the trivial +/- duplicate.
    pivot = int(np.argmax(np.abs(p)))
    if p[pivot] < 0:
        p *= -1.0
    return p


def initialize_dictionary_from_signal(
    signal: np.ndarray,
    scales: Sequence[int] = (16, 32, 64),
    atoms_per_scale: int = 4,
    *,
    seed: int = 0,
    candidate_limit: int = 512,
    remove_mean: bool = False,
    min_rms: float = 1e-5,
) -> list[np.ndarray]:
    """Build a deterministic multi-scale dictionary from signal patches.

    Candidate patches are sampled across the signal. A greedy farthest-point
    selection prefers low mutual coherence (large waveform-shape diversity).
    The resulting atoms are empirical time-domain templates, not Fourier bins.
    This is an initializer, not a converged dictionary-learning algorithm.
    """
    x = np.asarray(signal, dtype=np.float64)
    if x.ndim != 1 or not np.all(np.isfinite(x)):
        raise ValueError("signal must be a finite 1-D array")
    if atoms_per_scale < 1 or candidate_limit < atoms_per_scale:
        raise ValueError("invalid atom or candidate count")
    rng = np.random.default_rng(seed)
    result: list[np.ndarray] = []
    for length in scales:
        length = int(length)
        if length < 2:
            raise ValueError("every atom length must be at least 2")
        if x.size < length:
            continue
        possible = np.arange(0, x.size - length + 1, max(1, length // 4), dtype=np.int64)
        if possible.size > candidate_limit:
            possible = np.sort(rng.choice(possible, size=candidate_limit, replace=False))
        candidates: list[np.ndarray] = []
        candidate_energies: list[float] = []
        for start in possible:
            patch = x[start:start + length]
            if float(np.sqrt(np.mean(patch * patch))) < min_rms:
                continue
            normed = _normalise_patch(patch, remove_mean)
            if normed is not None:
                candidates.append(normed)
                candidate_energies.append(float(np.linalg.norm(patch)))
        if not candidates:
            continue
        matrix = np.stack(candidates)
        # First atom = highest-energy original patch. Then maximise minimum
        # distance up to sign, equivalent to minimising maximum |correlation|.
        norms = np.asarray(candidate_energies, dtype=np.float64)
        selected: list[int] = [int(np.argmax(norms))]
        while len(selected) < min(atoms_per_scale, len(candidates)):
            coherence = np.max(np.abs(matrix @ matrix[selected].T), axis=1)
            coherence[selected] = np.inf
            idx = int(np.argmin(coherence))
            selected.append(idx)
        result.extend(matrix[i].copy() for i in selected)
    if not result:
        raise ValueError("could not initialise atoms: signal is too short or below min_rms")
    return result
