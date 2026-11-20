"""Waveform-domain reconstruction metrics."""
from __future__ import annotations
import numpy as np


def snr_db(reference: np.ndarray, estimate: np.ndarray) -> float:
    x = np.asarray(reference, dtype=np.float64)
    y = np.asarray(estimate, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("reference and estimate shapes differ")
    signal_energy = float(np.dot(x.ravel(), x.ravel()))
    error = x - y
    error_energy = float(np.dot(error.ravel(), error.ravel()))
    if error_energy == 0:
        return float("inf")
    if signal_energy == 0:
        return float("-inf")
    return 10.0 * np.log10(signal_energy / error_energy)


def relative_l2_error(reference: np.ndarray, estimate: np.ndarray) -> float:
    x = np.asarray(reference, dtype=np.float64)
    y = np.asarray(estimate, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("reference and estimate shapes differ")
    return float(np.linalg.norm(x - y) / max(np.linalg.norm(x), 1e-30))


def max_abs_error(reference: np.ndarray, estimate: np.ndarray) -> float:
    x = np.asarray(reference, dtype=np.float64)
    y = np.asarray(estimate, dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("reference and estimate shapes differ")
    return float(np.max(np.abs(x - y), initial=0.0))
