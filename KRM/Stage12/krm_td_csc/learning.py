"""Alternating time-domain convolutional dictionary learning (CDL).

This reference implementation uses only finite linear convolutions in time.
It deliberately avoids FFT/STFT/DCT operations so that the model, adjoint,
normalisation constraints, and boundary handling remain transparent.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Sequence

import numpy as np

from .operators import forward
from .solver import SolverResult, estimate_lipschitz, solve_cbpdn_fista

Array = np.ndarray


def _as_signals(signals: Sequence[Array]) -> list[Array]:
    if not signals:
        raise ValueError("at least one training signal is required")
    result: list[Array] = []
    for index, signal in enumerate(signals):
        x = np.asarray(signal, dtype=np.float64)
        if x.ndim != 1 or x.size < 2 or not np.all(np.isfinite(x)):
            raise ValueError(f"signal {index} must be finite 1-D with at least two samples")
        # Inputs are read-only during dictionary learning; avoid copying long
        # training sequences on every objective/gradient evaluation.
        result.append(x)
    return result


def _as_atoms(atoms: Sequence[Array]) -> list[Array]:
    """Copy and normalise initial atoms before optimisation starts."""
    if not atoms:
        raise ValueError("at least one atom is required")
    result: list[Array] = []
    for index, atom in enumerate(atoms):
        d = np.asarray(atom, dtype=np.float64)
        if d.ndim != 1 or d.size < 2 or not np.all(np.isfinite(d)):
            raise ValueError(f"atom {index} must be finite 1-D with at least two samples")
        norm = float(np.linalg.norm(d))
        if norm < 1e-12:
            raise ValueError(f"atom {index} has near-zero norm")
        result.append(d.copy() / norm)
    return result


def _validate_unit_atoms(atoms: Sequence[Array]) -> list[Array]:
    """Validate the unit-sphere constraint without silently changing values."""
    if not atoms:
        raise ValueError("at least one atom is required")
    result: list[Array] = []
    for index, atom in enumerate(atoms):
        d = np.asarray(atom, dtype=np.float64)
        if d.ndim != 1 or d.size < 2 or not np.all(np.isfinite(d)):
            raise ValueError(f"atom {index} must be finite 1-D with at least two samples")
        norm = float(np.linalg.norm(d))
        if not np.isclose(norm, 1.0, rtol=1e-6, atol=1e-8):
            raise ValueError(f"atom {index} must have unit L2 norm; got {norm:.9g}")
        result.append(d)
    return result


def dictionary_smooth_loss(
    signals: Sequence[Array],
    coefficients: Sequence[Sequence[Array]],
    atoms: Sequence[Array],
) -> float:
    """Return 0.5 * sum_s ||A_D(a_s)-x_s||_2^2."""
    xs = _as_signals(signals)
    ds = _validate_unit_atoms(atoms)
    if len(coefficients) != len(xs):
        raise ValueError("one coefficient collection is required per signal")
    total = 0.0
    for index, (x, maps) in enumerate(zip(xs, coefficients)):
        if len(maps) != len(ds):
            raise ValueError(f"signal {index}: coefficient-map count differs from atom count")
        residual = forward(maps, ds, x.size) - x
        total += 0.5 * float(np.dot(residual, residual))
    return total


def dictionary_learning_objective(
    signals: Sequence[Array],
    coefficients: Sequence[Sequence[Array]],
    atoms: Sequence[Array],
    lam: float,
) -> float:
    """Return reconstruction loss plus the shared L1 activation penalty."""
    if lam < 0 or not np.isfinite(lam):
        raise ValueError("lam must be finite and non-negative")
    smooth = dictionary_smooth_loss(signals, coefficients, atoms)
    sparse = sum(float(np.sum(np.abs(a))) for maps in coefficients for a in maps)
    return smooth + lam * sparse


def dictionary_gradient(
    signals: Sequence[Array],
    coefficients: Sequence[Sequence[Array]],
    atoms: Sequence[Array],
) -> list[Array]:
    """Exact gradient of the smooth dictionary loss for finite full-overlap maps.

    For an atom d_k of length L and its activation map a_k, the model uses
    y[n] += sum_j d[j] * a[n + L - 1 - j]. Thus grad[j] is the dot product
    between the signal residual and that aligned activation-map slice.
    """
    xs = _as_signals(signals)
    ds = _validate_unit_atoms(atoms)
    if len(coefficients) != len(xs):
        raise ValueError("one coefficient collection is required per signal")
    grads = [np.zeros_like(d) for d in ds]
    for signal_index, (x, maps) in enumerate(zip(xs, coefficients)):
        if len(maps) != len(ds):
            raise ValueError(f"signal {signal_index}: coefficient-map count differs from atom count")
        residual = forward(maps, ds, x.size) - x
        for k, (atom, activation) in enumerate(zip(ds, maps)):
            a = np.asarray(activation, dtype=np.float64)
            expected = x.size + atom.size - 1
            if a.ndim != 1 or a.size != expected or not np.all(np.isfinite(a)):
                raise ValueError(f"signal {signal_index}: activation map {k} must be finite length {expected}")
            left = atom.size - 1
            for j in range(atom.size):
                start = left - j
                grads[k][j] += float(np.dot(residual, a[start:start + x.size]))
    return grads


def _projected_sphere_gradients(atoms: Sequence[Array], gradients: Sequence[Array]) -> list[Array]:
    projected: list[Array] = []
    for d, g in zip(atoms, gradients):
        # Riemannian gradient on the unit sphere: remove its normal component.
        projected.append(g - float(np.dot(g, d)) * d)
    return projected


def _sphere_retract(atoms: Sequence[Array], directions: Sequence[Array], step: float) -> list[Array]:
    updated: list[Array] = []
    for d, direction in zip(atoms, directions):
        candidate = d - step * direction
        norm = float(np.linalg.norm(candidate))
        if norm < 1e-12 or not np.isfinite(norm):
            updated.append(d.copy())
        else:
            updated.append(candidate / norm)
    return updated


@dataclass
class DictionaryLearningResult:
    atoms: list[Array]
    coefficients: list[list[Array]]
    objective_history: list[float]
    smooth_loss_history: list[float]
    dictionary_step_history: list[float]
    dictionary_gradient_norm_history: list[float]
    coding_iterations: list[int]
    coding_converged: list[bool]
    coding_optimality_residuals: list[float]
    iterations: int
    converged: bool
    inactive_atoms: list[int]
    elapsed_seconds: float


def learn_convolutional_dictionary(
    signals: Sequence[Array],
    initial_atoms: Sequence[Array],
    *,
    lam: float = 0.01,
    outer_iterations: int = 20,
    coding_iterations: int = 150,
    coding_tolerance: float = 1e-5,
    dictionary_tolerance: float = 1e-6,
    initial_dictionary_step: float = 100.0,
    max_dictionary_backtracking: int = 30,
    power_iterations: int = 30,
    seed: int = 0,
) -> DictionaryLearningResult:
    """Learn a shared waveform dictionary by alternating sparse coding/update.

    Each outer iteration:
      1. solve each signal's CBPDN coefficients with FISTA (warm-started),
      2. update all unit-norm atoms with a projected-gradient step and
         non-increasing backtracking line search.

    The objective is 0.5*sum_s||A_D(a_s)-x_s||^2 + lam*sum_s,k||a_s,k||_1.
    This is a non-convex alternating method; convergence to a global optimum or
    recovery of a unique physical source decomposition is not guaranteed.
    Different training signals may have different sample lengths, but the
    dictionary atom lengths are shared.
    """
    start_time = time.perf_counter()
    xs = _as_signals(signals)
    atoms = _as_atoms(initial_atoms)
    if lam < 0 or not np.isfinite(lam):
        raise ValueError("lam must be finite and non-negative")
    if outer_iterations < 1 or coding_iterations < 1:
        raise ValueError("iteration limits must be positive")
    numeric_settings = (coding_tolerance, dictionary_tolerance, initial_dictionary_step)
    if not all(np.isfinite(value) for value in numeric_settings):
        raise ValueError("tolerances and dictionary step must be finite")
    if coding_tolerance <= 0 or dictionary_tolerance <= 0:
        raise ValueError("tolerances must be positive")
    if initial_dictionary_step <= 0 or max_dictionary_backtracking < 1:
        raise ValueError("invalid dictionary line-search configuration")

    codes: list[list[Array]] = [
        [np.zeros(x.size + d.size - 1, dtype=np.float64) for d in atoms]
        for x in xs
    ]
    objective_history: list[float] = []
    smooth_history: list[float] = []
    step_history: list[float] = []
    grad_norm_history: list[float] = []
    coding_iter_history: list[int] = []
    coding_converged_history: list[bool] = []
    coding_optimality_history: list[float] = []
    converged = False
    previous_objective = float("inf")
    final_iteration = 0

    for outer in range(1, outer_iterations + 1):
        final_iteration = outer
        # Sparse-coding step. Warm starts are valid because atom lengths remain fixed.
        new_codes: list[list[Array]] = []
        outer_coding_all_converged = True
        # The FISTA Lipschitz constant depends on the dictionary and signal
        # length, not on signal content. Cache one estimate per distinct length
        # within this outer iteration instead of recomputing it for every
        # training example (especially useful for stereo/shared-dictionary data).
        lipschitz_by_length: dict[int, float] = {}
        for x, warm in zip(xs, codes):
            if x.size not in lipschitz_by_length:
                lipschitz_by_length[x.size] = estimate_lipschitz(
                    atoms, x.size, iterations=power_iterations,
                    seed=seed + outer + x.size,
                )
            solved: SolverResult = solve_cbpdn_fista(
                x, atoms, lam=lam, max_iterations=coding_iterations,
                tolerance=coding_tolerance, power_iterations=power_iterations,
                initial_lipschitz=lipschitz_by_length[x.size],
                initial_coefficients=warm, seed=seed + outer,
            )
            new_codes.append(solved.coefficients)
            outer_coding_all_converged = outer_coding_all_converged and solved.converged
            coding_iter_history.append(solved.iterations)
            coding_converged_history.append(solved.converged)
            coding_optimality_history.append(solved.optimality_residual)
        codes = new_codes

        before = dictionary_learning_objective(xs, codes, atoms, lam)
        smooth_before = dictionary_smooth_loss(xs, codes, atoms)
        gradients = dictionary_gradient(xs, codes, atoms)
        projected = _projected_sphere_gradients(atoms, gradients)
        grad_norm = float(np.sqrt(sum(float(np.dot(g, g)) for g in projected)))
        grad_norm_history.append(grad_norm)

        accepted_atoms = [d.copy() for d in atoms]
        accepted_step = 0.0
        if grad_norm > dictionary_tolerance:
            step = initial_dictionary_step
            for _ in range(max_dictionary_backtracking):
                candidate = _sphere_retract(atoms, projected, step)
                candidate_smooth = dictionary_smooth_loss(xs, codes, candidate)
                # Armijo decrease using the projected-gradient norm. The sphere
                # retraction is first-order equivalent to this tangent step.
                armijo_bound = smooth_before - 1e-4 * step * grad_norm * grad_norm
                if candidate_smooth <= armijo_bound + 1e-13 * max(1.0, smooth_before):
                    accepted_atoms = candidate
                    accepted_step = step
                    break
                step *= 0.5
        atoms = accepted_atoms
        step_history.append(accepted_step)
        smooth_after = dictionary_smooth_loss(xs, codes, atoms)
        objective = smooth_after + lam * sum(
            float(np.sum(np.abs(a))) for maps in codes for a in maps
        )
        # Numerical tolerance only; this is expected to be non-increasing because
        # FISTA is monotone and dictionary updates have an Armijo backtracking test.
        if objective > before + 1e-9 * max(1.0, before):
            raise RuntimeError("alternating CDL objective increased unexpectedly")
        objective_history.append(objective)
        smooth_history.append(smooth_after)

        relative_change = (
            abs(previous_objective - objective) / max(1.0, abs(previous_objective))
            if np.isfinite(previous_objective) else float("inf")
        )
        if (outer > 1 and relative_change <= dictionary_tolerance
                and accepted_step == 0.0 and outer_coding_all_converged):
            converged = True
            break
        previous_objective = objective

    # Recompute activity from the final coefficient maps. Zero-activity atoms
    # cannot receive a meaningful update and are explicitly reported.
    activity = [
        sum(float(np.sum(np.abs(maps[k]))) for maps in codes)
        for k in range(len(atoms))
    ]
    max_activity = max(activity, default=0.0)
    inactive = [k for k, value in enumerate(activity) if value <= max(1e-10, max_activity * 1e-8)]

    return DictionaryLearningResult(
        atoms=atoms,
        coefficients=codes,
        objective_history=objective_history,
        smooth_loss_history=smooth_history,
        dictionary_step_history=step_history,
        dictionary_gradient_norm_history=grad_norm_history,
        coding_iterations=coding_iter_history,
        coding_converged=coding_converged_history,
        coding_optimality_residuals=coding_optimality_history,
        iterations=final_iteration,
        converged=converged,
        inactive_atoms=inactive,
        elapsed_seconds=time.perf_counter() - start_time,
    )
