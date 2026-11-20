"""Matrix-free, direct-time-domain ADMM solver for multi-scale CBPDN."""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Sequence
import numpy as np

from .operators import adjoint, coefficient_lengths, forward
from .solver import soft_threshold


@dataclass
class ADMMResult:
    coefficients: list[np.ndarray]
    reconstruction: np.ndarray
    residual: np.ndarray
    objective_history: list[float]
    primal_history: list[float]
    dual_history: list[float]
    iterations: int
    converged: bool
    total_cg_iterations: int
    elapsed_seconds: float
    rho_history: list[float]


def _dot(a: Sequence[np.ndarray], b: Sequence[np.ndarray]) -> float:
    return sum(float(np.dot(x, y)) for x, y in zip(a, b))


def _norm(a: Sequence[np.ndarray]) -> float:
    return float(np.sqrt(max(0.0, _dot(a, a))))


def _add(a: Sequence[np.ndarray], b: Sequence[np.ndarray], alpha: float = 1.0) -> list[np.ndarray]:
    return [x + alpha * y for x, y in zip(a, b)]


def _scale(a: Sequence[np.ndarray], alpha: float) -> list[np.ndarray]:
    return [alpha * x for x in a]


def _cg_solve(
    rhs: Sequence[np.ndarray],
    atoms: Sequence[np.ndarray],
    signal_length: int,
    rho: float,
    *,
    x0: Sequence[np.ndarray] | None = None,
    tolerance: float = 1e-5,
    max_iterations: int = 100,
) -> tuple[list[np.ndarray], int]:
    """Solve (A* A + rho I)x=rhs with matrix-free conjugate gradients."""
    x = [np.zeros_like(v) for v in rhs] if x0 is None else [v.copy() for v in x0]

    def apply(v: Sequence[np.ndarray]) -> list[np.ndarray]:
        av = forward(v, atoms, signal_length)
        return _add(adjoint(av, atoms), v, rho)

    r = _add(rhs, apply(x), -1.0)
    p = [v.copy() for v in r]
    rr = _dot(r, r)
    rhs_norm = max(_norm(rhs), 1e-30)
    if np.sqrt(rr) <= tolerance * rhs_norm:
        return x, 0
    for iteration in range(1, max_iterations + 1):
        ap = apply(p)
        denom = _dot(p, ap)
        if denom <= 0 or not np.isfinite(denom):
            raise RuntimeError("CG encountered a non-positive curvature direction")
        alpha = rr / denom
        x = _add(x, p, alpha)
        r = _add(r, ap, -alpha)
        rr_new = _dot(r, r)
        if np.sqrt(max(rr_new, 0.0)) <= tolerance * rhs_norm:
            return x, iteration
        beta = rr_new / max(rr, 1e-300)
        p = _add(r, p, beta)
        rr = rr_new
    return x, max_iterations


def solve_cbpdn_admm(
    signal: np.ndarray,
    atoms: Sequence[np.ndarray],
    *,
    lam: float = 0.02,
    rho: float = 1.0,
    max_iterations: int = 150,
    cg_tolerance: float = 2e-5,
    cg_max_iterations: int = 80,
    abs_tolerance: float = 1e-5,
    rel_tolerance: float = 1e-4,
    adaptive_rho: bool = True,
    rho_update_interval: int = 10,
    rho_balance: float = 10.0,
    rho_scale: float = 2.0,
) -> ADMMResult:
    """Solve CBPDN by ADMM with a direct-time-domain matrix-free CG x-step.

    The model contains only finite linear convolutions/correlations. No FFT or
    other frequency-domain transform is used by this solver.
    """
    x = np.asarray(signal, dtype=np.float64)
    ds = [np.asarray(d, dtype=np.float64) for d in atoms]
    if x.ndim != 1 or x.size == 0 or not np.all(np.isfinite(x)):
        raise ValueError("signal must be non-empty, finite, and one-dimensional")
    if not ds or any(d.ndim != 1 or d.size < 2 or not np.all(np.isfinite(d)) for d in ds):
        raise ValueError("atoms must be non-empty finite 1-D arrays of length >= 2")
    if any(not np.isclose(np.linalg.norm(d), 1.0, rtol=1e-6, atol=1e-8) for d in ds):
        raise ValueError("all atoms must be unit L2 norm")
    if lam < 0 or rho <= 0 or max_iterations < 1:
        raise ValueError("invalid lambda, rho, or iteration count")

    start = time.perf_counter()
    n = x.size
    shape = len(ds)
    map_lengths = coefficient_lengths(n, ds)
    a = [np.zeros(length, dtype=np.float64) for length in map_lengths]
    z = [v.copy() for v in a]
    u = [v.copy() for v in a]
    atx = adjoint(x, ds)
    history: list[float] = []
    primal_hist: list[float] = []
    dual_hist: list[float] = []
    total_cg = 0
    converged = False
    rho_values: list[float] = []
    count = sum(map_lengths)

    for iteration in range(1, max_iterations + 1):
        rhs = _add(atx, _add(z, u, -1.0), rho)
        a, cg_count = _cg_solve(
            rhs, ds, n, rho, x0=a, tolerance=cg_tolerance,
            max_iterations=cg_max_iterations,
        )
        total_cg += cg_count
        z_old = [v.copy() for v in z]
        z = [soft_threshold(av + uv, lam / rho) for av, uv in zip(a, u)]
        u = _add(u, _add(a, z, -1.0))

        primal = _norm(_add(a, z, -1.0))
        dual = rho * _norm(_add(z, z_old, -1.0))
        recon = forward(z, ds, n)
        residual = recon - x
        objective = 0.5 * float(np.dot(residual, residual)) + lam * sum(float(np.sum(np.abs(v))) for v in z)
        history.append(objective)
        primal_hist.append(primal)
        dual_hist.append(dual)
        rho_values.append(rho)

        eps_primal = np.sqrt(count) * abs_tolerance + rel_tolerance * max(_norm(a), _norm(z))
        eps_dual = np.sqrt(count) * abs_tolerance + rel_tolerance * rho * _norm(u)
        if primal <= eps_primal and dual <= eps_dual:
            converged = True
            break

        if adaptive_rho and iteration % max(1, rho_update_interval) == 0:
            old_rho = rho
            if primal > rho_balance * max(dual, 1e-30):
                rho *= rho_scale
            elif dual > rho_balance * max(primal, 1e-30):
                rho /= rho_scale
            if rho != old_rho:
                # Preserve the unscaled dual variable y = rho*u.
                u = _scale(u, old_rho / rho)

    recon = forward(z, ds, n)
    return ADMMResult(
        coefficients=z,
        reconstruction=recon,
        residual=x - recon,
        objective_history=history,
        primal_history=primal_hist,
        dual_history=dual_hist,
        iterations=iteration,
        converged=converged,
        total_cg_iterations=total_cg,
        elapsed_seconds=time.perf_counter() - start,
        rho_history=rho_values,
    )
