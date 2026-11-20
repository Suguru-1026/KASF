# KRM Time-Domain CSC/CDL Benchmark Report — Draft 0.8

Date: 2026-11-14

## Automated validation

- Full suite: 66/66 tests passed.
- Python compileall: passed.
- Solver and CDL numerical tests include adjoint identity, finite-difference atom gradients, unit-norm constraints, non-increasing penalised objective, deterministic execution, FISTA warm starts and proximal-gradient mapping convergence checks. Outer CDL convergence also requires all inner FISTA solves from the final outer iteration to converge; non-finite optimisation settings are rejected.
- Research solver package statically checked for FFT/STFT/DCT calls; none are used by `krm_td_csc`.

## Main algorithm added

Draft 0.8 adds alternating time-domain Convolutional Dictionary Learning (CDL). It alternates monotone FISTA coefficient updates (warm-started) with a projected-gradient dictionary update constrained to unit-L2 atoms. The dictionary step uses Armijo backtracking. Lipschitz estimates are cached by signal length within each outer iteration.

FISTA convergence now checks the proximal-gradient mapping as an approximate KKT fixed-point residual when the coefficient step becomes small. The absolute residual is exposed in `SolverResult.optimality_residual` and included in dictionary-learning diagnostics. A small iterate change alone no longer triggers `converged=True`.

## Validation experiments

Two pre-existing Library PCM WAVs were used without modifying the originals. The 48 kHz mono source and 44.1 kHz stereo source were divided into deterministic, time-distributed train and held-out validation windows. Stereo channels were independent training examples sharing one dictionary; no joint-stereo constraints were used. The initial dictionary used training segments only. The validation windows did not influence atom initialization or dictionary updates.

### Atom length 24, segment length 512

| Source | Validation SNR before | Validation SNR after | Change | Relative L2 before | Relative L2 after |
|---|---:|---:|---:|---:|---:|
| 48 kHz mono | 13.540 dB | 13.667 dB | +0.127 dB | 0.21037 | 0.20733 |
| 44.1 kHz stereo | 17.988 dB | 20.322 dB | +2.334 dB | 0.12606 | 0.09636 |

### Atom length 64, segment length 1024

| Source | Validation SNR before | Validation SNR after | Change | Relative L2 before | Relative L2 after |
|---|---:|---:|---:|---:|---:|
| 48 kHz mono | 10.874 dB | 11.909 dB | +1.035 dB | 0.28596 | 0.25382 |
| 44.1 kHz stereo | 14.335 dB | 16.472 dB | +2.137 dB | 0.19197 | 0.15010 |

### Matched parameter-count comparison, segment length 2048

Both models use 384 atom samples/parameters in total on the 44.1 kHz stereo source.

| Atom length/count | Validation SNR before | Validation SNR after | Relative L2 before | Relative L2 after |
|---|---:|---:|---:|---:|
| 64 / 6 | 10.087 dB | 10.403 dB | 0.31308 | 0.30189 |
| 128 / 3 | 6.556 dB | 7.747 dB | 0.47009 | 0.40985 |

This one split favoured 64-sample atoms. It does not establish a general optimum atom length. These 2048-sample runs were capped at 35 coefficient iterations and none of those FISTA subproblems met the requested stopping criterion.

## Single-window KKT diagnostic

For one 512-sample channel segment from the 44.1 kHz stereo WAV, with six 24-sample atoms and lambda `1.0761806180872601e-4`, FISTA was tested at increasing iteration caps. It met the approximate proximal-gradient mapping tolerance at iteration 441:

- 80 iterations: not converged; mapping norm `2.6914814212712567e-4`.
- 200 iterations: not converged; mapping norm `6.849772830601254e-5`.
- 500 cap: converged at 441; mapping norm `9.899120603835852e-6`.

This illustrates why a fixed 35–80 iteration benchmark cap must be reported as an early-stop exploration rather than a converged coding solution.

## Runtime observations

On the current development execution environment, the 1024-sample / 64-sample-atom benchmark took approximately:

- 1.39 s baseline train+validation encoding and 3.79 s dictionary learning for Source A.
- 2.18 s baseline train+validation encoding and 7.86 s dictionary learning for Source B.

Times are machine-specific and are not predictions for the user's Chromebook or other hardware. Caching the Lipschitz estimate by signal length avoids recalculating the same power iteration for every same-length training example in each outer iteration.

## Interpretation

- The learned dictionaries improved held-out validation metrics in these experiments, but gains were content- and configuration-dependent.
- The 48 kHz mono 512/24 case improved only slightly; the 44.1 kHz stereo 512/24 case improved more substantially.
- Longer atoms did not automatically improve validation quality. Under equal total atom samples in one 2048-sample split, six 64-sample atoms outperformed three 128-sample atoms.
- Some coding subproblems did not converge at the selected iteration cap. Their `optimality_residual` must be inspected; the outer objective's monotonic descent does not turn an unfinished inner solve into an optimal one.
- The algorithm is non-convex jointly in atoms and activations. The current projected-gradient + Armijo dictionary update is a reference baseline, not a state-of-the-art or globally optimal solver.
- KASF, KRC, and KRM-IF remain unintegrated with this research track. No frequency-domain translation is used.

## Next work

1. Compare global FISTA against slice-based / LoBCoD-style time-domain coordinate updates.
2. Implement an explicit residual-error-budget form of CSC (`epsilon`-constrained) and compare it with lambda-penalised CBPDN.
3. Add dead-atom recovery, coherence diagnostics and controlled redundancy management.
4. Improve solver speed so the coding subproblems can reach comparable KKT tolerances on longer atoms.
5. Expand held-out audio tests and only then evaluate true multi-scale and joint-stereo dictionary learning.

## Artifacts

- Main protocol: `benchmarks/run_dictionary_learning.py`
- Main metrics: `benchmarks/dictionary-learning-draft-0.8.json`
- 64-sample atoms: `benchmarks/dictionary-learning-scale64-draft-0.8.json`
- 2048-sample matched parameter comparison: `benchmarks/dictionary-learning-scale64-2048-comparison.json`, `benchmarks/dictionary-learning-scale128-exploratory.json`
