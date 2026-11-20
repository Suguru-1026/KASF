"""Monotone backtracking FISTA for time-domain multi-scale CBPDN."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import time
import numpy as np

from .operators import adjoint, coefficient_lengths, forward


@dataclass
class SolverResult:
    coefficients: list[np.ndarray]
    reconstruction: np.ndarray
    residual: np.ndarray
    objective_history: list[float]
    iterations: int
    converged: bool
    lipschitz_estimate: float
    elapsed_seconds: float
    sparsity_nonzero: int
    sparsity_total: int
    optimality_residual: float


def soft_threshold(x: np.ndarray, threshold: float) -> np.ndarray:
    return np.sign(x) * np.maximum(np.abs(x) - threshold, 0.0)


def estimate_lipschitz(
    atoms: Sequence[np.ndarray],
    signal_length: int,
    *,
    iterations: int = 40,
    seed: int = 0,
) -> float:
    """Power-iteration estimate of ||A||^2, with exact time-domain A and A*."""
    rng = np.random.default_rng(seed)
    map_lengths = coefficient_lengths(signal_length, atoms)
    v = [rng.standard_normal(length) for length in map_lengths]
    norm = np.sqrt(sum(float(np.dot(z, z)) for z in v))
    if norm == 0:
        return 1.0
    v = [z / norm for z in v]
    eigenvalue = 0.0
    for _ in range(max(1, iterations)):
        av = forward(v, atoms, signal_length)
        z = adjoint(av, atoms)
        znorm = np.sqrt(sum(float(np.dot(q, q)) for q in z))
        if znorm <= 1e-30:
            return 1.0
        v = [q / znorm for q in z]
        eigenvalue = float(np.dot(forward(v, atoms, signal_length), forward(v, atoms, signal_length)))
    return max(eigenvalue, 1e-12)


def _objective(xhat: np.ndarray, target: np.ndarray, coeffs: Sequence[np.ndarray], lam: float) -> float:
    residual = xhat - target
    return 0.5 * float(np.dot(residual, residual)) + lam * sum(float(np.sum(np.abs(a))) for a in coeffs)


def _smooth_value(xhat: np.ndarray, target: np.ndarray) -> float:
    r = xhat - target
    return 0.5 * float(np.dot(r, r))


def _candidate_step(
    y: Sequence[np.ndarray],
    target: np.ndarray,
    atoms: Sequence[np.ndarray],
    lam: float,
    lipschitz: float,
    *,
    max_backtracking: int = 30,
) -> tuple[list[np.ndarray], float, np.ndarray, float]:
    """Proximal-gradient step satisfying the smooth majorisation inequality."""
    ay = forward(y, atoms, target.size)
    smooth_y = _smooth_value(ay, target)
    residual = ay - target
    grad = adjoint(residual, atoms)
    for _ in range(max_backtracking):
        candidate = [soft_threshold(a - g / lipschitz, lam / lipschitz) for a, g in zip(y, grad)]
        delta = [c - a for c, a in zip(candidate, y)]
        linear = sum(float(np.dot(g, d)) for g, d in zip(grad, delta))
        delta_norm2 = sum(float(np.dot(d, d)) for d in delta)
        ax = forward(candidate, atoms, target.size)
        smooth_x = _smooth_value(ax, target)
        bound = smooth_y + linear + 0.5 * lipschitz * delta_norm2 + 1e-12 * max(1.0, smooth_y)
        if smooth_x <= bound:
            obj = _objective(ax, target, candidate, lam)
            return candidate, obj, ax, lipschitz
        lipschitz *= 2.0
    raise RuntimeError("backtracking failed to find a valid majoriser")


def solve_cbpdn_fista(
    signal: np.ndarray,
    atoms: Sequence[np.ndarray],
    *,
    lam: float = 0.02,
    max_iterations: int = 300,
    tolerance: float = 1e-5,
    power_iterations: int = 40,
    monotone: bool = True,
    initial_lipschitz: float | None = None,
    initial_coefficients: Sequence[np.ndarray] | None = None,
    seed: int = 0,
) -> SolverResult:
    """Solve 0.5||sum_k d_k*a_k - x||_2^2 + lam*sum_k||a_k||_1.

    The linear operators are evaluated with direct finite-length time-domain
    convolution/correlation. Different atom lengths are allowed, making this
    a multi-scale CSC solver. Boundary policy is zero-extension followed by
    cropping to the observed signal interval.
    """
    x = np.asarray(signal, dtype=np.float64)
    ds = [np.asarray(d, dtype=np.float64) for d in atoms]
    if x.ndim != 1 or x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError("signal must be non-empty, finite, and one-dimensional")
    if not ds or any(d.ndim != 1 or d.size < 2 or not np.all(np.isfinite(d)) for d in ds):
        raise ValueError("atoms must be non-empty finite 1-D arrays of length >= 2")
    norms = [float(np.linalg.norm(d)) for d in ds]
    if any(not np.isclose(v, 1.0, rtol=1e-6, atol=1e-8) for v in norms):
        raise ValueError("all atoms must be unit L2 norm")
    if lam < 0 or not np.isfinite(lam):
        raise ValueError("lam must be finite and non-negative")
    if max_iterations < 1 or tolerance <= 0:
        raise ValueError("invalid iteration limit or tolerance")

    start = time.perf_counter()
    n = x.size
    map_lengths = coefficient_lengths(n, ds)
    L = float(initial_lipschitz or estimate_lipschitz(ds, n, iterations=power_iterations, seed=seed))
    if initial_coefficients is None:
        coeffs = [np.zeros(length, dtype=np.float64) for length in map_lengths]
    else:
        if len(initial_coefficients) != len(map_lengths):
            raise ValueError("initial coefficient-map count must equal atom count")
        coeffs = []
        for index, (value, expected) in enumerate(zip(initial_coefficients, map_lengths)):
            arr = np.asarray(value, dtype=np.float64)
            if arr.ndim != 1 or arr.size != expected or not np.all(np.isfinite(arr)):
                raise ValueError(f"initial coefficient map {index} must be finite 1-D length {expected}")
            coeffs.append(arr.copy())
    y = [a.copy() for a in coeffs]
    t = 1.0
    history: list[float] = []
    converged = False
    initial_reconstruction = forward(coeffs, ds, n)
    prev_obj = _objective(initial_reconstruction, x, coeffs, lam)
    prev_recon = initial_reconstruction

    for iteration in range(1, max_iterations + 1):
        candidate, obj, recon, L = _candidate_step(y, x, ds, lam, L)
        if monotone and obj > prev_obj + 1e-12 * max(1.0, prev_obj):
            # Adaptive restart: discard accumulated momentum and step from x_k.
            y = [a.copy() for a in coeffs]
            t = 1.0
            candidate, obj, recon, L = _candidate_step(y, x, ds, lam, L)
        diff_norm = np.sqrt(sum(float(np.dot(c - a, c - a)) for c, a in zip(candidate, coeffs)))
        coeff_norm = np.sqrt(sum(float(np.dot(c, c)) for c in candidate))
        history.append(obj)
        coeffs_old = coeffs
        coeffs = candidate
        if diff_norm <= tolerance * max(1.0, coeff_norm):
            # A small iterate change alone can be misleading (for example,
            # under a poor step-size estimate). Confirm approximate KKT
            # stationarity with the proximal-gradient mapping before declaring
            # convergence.
            candidate_residual = recon - x
            candidate_gradient = adjoint(candidate_residual, ds)
            proximal = [
                soft_threshold(a - g / L, lam / L)
                for a, g in zip(coeffs, candidate_gradient)
            ]
            mapping_norm = L * np.sqrt(sum(
                float(np.dot(a - p, a - p)) for a, p in zip(coeffs, proximal)
            ))
            if mapping_norm <= tolerance * max(1.0, coeff_norm):
                converged = True
                prev_recon = recon
                break
        t_next = 0.5 * (1.0 + np.sqrt(1.0 + 4.0 * t * t))
        y = [c + ((t - 1.0) / t_next) * (c - old) for c, old in zip(coeffs, coeffs_old)]
        t = t_next
        prev_obj = obj
        prev_recon = recon

    recon = forward(coeffs, ds, n)
    residual = x - recon
    nonzero = sum(int(np.count_nonzero(np.abs(a) > 1e-8)) for a in coeffs)
    total = sum(map_lengths)
    final_gradient = adjoint(recon - x, ds)
    final_proximal = [
        soft_threshold(a - g / L, lam / L)
        for a, g in zip(coeffs, final_gradient)
    ]
    optimality_residual = float(L * np.sqrt(sum(
        float(np.dot(a - p, a - p)) for a, p in zip(coeffs, final_proximal)
    )))
    return SolverResult(
        coefficients=coeffs,
        reconstruction=recon,
        residual=residual,
        objective_history=history,
        iterations=iteration,
        converged=converged,
        lipschitz_estimate=L,
        elapsed_seconds=time.perf_counter() - start,
        sparsity_nonzero=nonzero,
        sparsity_total=total,
        optimality_residual=optimality_residual,
    )
