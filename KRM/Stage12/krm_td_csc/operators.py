"""Finite-support, full-overlap convolution operators implemented directly in time.

For an observed N-sample signal and atom d_k of length L_k, the coefficient
map a_k has length N+L_k-1. Map index t represents an atom start at absolute
sample t-(L_k-1), so every atom location that overlaps the observed signal is
represented exactly once. The output is

    y[n] = sum_k sum_j d_k[j] * a_k[n + (L_k-1) - j], 0 <= n < N,

with map values outside their finite ranges equal to zero. Equivalently, each
full linear convolution is cropped to [L_k-1:L_k-1+N]. This permits atoms to
begin before the first observed sample and extend beyond the last sample.

No FFT, DCT, STFT, or frequency-domain representation is used here.
"""
from __future__ import annotations

from typing import Sequence
import numpy as np

Array = np.ndarray


def _validate_atoms(atoms: Sequence[Array]) -> list[Array]:
    if not atoms:
        raise ValueError("at least one atom is required")
    out: list[Array] = []
    for i, atom in enumerate(atoms):
        d = np.asarray(atom, dtype=np.float64)
        if d.ndim != 1 or d.size == 0:
            raise ValueError(f"atom {i} must be a non-empty 1-D array")
        if not np.all(np.isfinite(d)):
            raise ValueError(f"atom {i} contains non-finite values")
        norm = float(np.linalg.norm(d))
        if not np.isclose(norm, 1.0, rtol=1e-6, atol=1e-8):
            raise ValueError(f"atom {i} must be unit L2 norm; got {norm:.9g}")
        out.append(d)
    return out


def coefficient_lengths(signal_length: int, atoms: Sequence[Array]) -> list[int]:
    if signal_length < 0:
        raise ValueError("signal_length must be non-negative")
    ds = _validate_atoms(atoms)
    return [int(signal_length + d.size - 1) for d in ds]


def forward(coefficients: Sequence[Array], atoms: Sequence[Array], signal_length: int | None = None) -> Array:
    """Apply A(a)=sum_k crop_{Lk-1:Lk-1+N}(conv(a_k,d_k)) directly in time."""
    ds = _validate_atoms(atoms)
    if len(coefficients) != len(ds):
        raise ValueError("coefficient-map count must equal atom count")
    if signal_length is None:
        if not coefficients:
            raise ValueError("signal_length is required for empty coefficients")
        signal_length = int(np.asarray(coefficients[0]).size - ds[0].size + 1)
    if signal_length < 0:
        raise ValueError("signal_length must be non-negative")
    out = np.zeros(signal_length, dtype=np.float64)
    for i, (a0, d) in enumerate(zip(coefficients, ds)):
        a = np.asarray(a0, dtype=np.float64)
        expected = signal_length + d.size - 1
        if a.ndim != 1 or a.size != expected:
            raise ValueError(f"coefficient map {i} must be 1-D of length {expected}")
        if signal_length:
            pad = d.size - 1
            full = np.convolve(a, d, mode="full")
            out += full[pad:pad + signal_length]
    return out


def adjoint(residual: Array, atoms: Sequence[Array]) -> list[Array]:
    """Apply the exact adjoint of the full-overlap finite convolution operator."""
    r = np.asarray(residual, dtype=np.float64)
    if r.ndim != 1 or not np.all(np.isfinite(r)):
        raise ValueError("residual must be a finite 1-D array")
    ds = _validate_atoms(atoms)
    out: list[Array] = []
    for d in ds:
        pad = d.size - 1
        if r.size == 0:
            out.append(np.zeros(pad, dtype=np.float64))
        else:
            padded = np.pad(r, (pad, pad))
            out.append(np.correlate(padded, d, mode="valid"))
    return out


def inner_product_error(coefficients: Sequence[Array], atoms: Sequence[Array], residual: Array) -> float:
    """Return |<Aa,r>-<a,A*r>|, used to validate the implemented adjoint."""
    lhs = float(np.dot(forward(coefficients, atoms, len(residual)), residual))
    rhs_maps = adjoint(residual, atoms)
    rhs = sum(float(np.dot(a, g)) for a, g in zip(coefficients, rhs_maps))
    return abs(lhs - rhs)
