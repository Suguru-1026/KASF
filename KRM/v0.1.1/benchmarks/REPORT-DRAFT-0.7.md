# KRM TD-CSC Benchmark Report — Draft 0.7

## Summary

A direct-time-domain multi-scale CBPDN reference implementation was added. It uses variable-length waveform atoms, full-overlap finite convolution, a matched adjoint, monotone backtracking FISTA, and matrix-free ADMM with conjugate gradients. The solver sources make no FFT/STFT/DCT calls.

## Synthetic known-dictionary case

| Metric | FISTA | ADMM + direct CG |
|---|---:|---:|
| Iterations | 1,096 | 129 outer |
| Converged | Yes | Yes |
| Wall time | 0.680 s | 0.813 s |
| Objective | 0.0155234979 | 0.0155562164 |
| SNR | 39.831 dB | 39.516 dB |
| Relative L2 error | 0.0101961 | 0.0105728 |
| CG inner iterations | — | 1,892 |

Conditions: 512 samples; atom lengths 12, 24, 48, 24; 16 planted coefficient events; lambda 0.002. These are measurements in the current execution environment, not performance claims for the user's computer.

The two solvers reached very similar objective values. The source had 16 planted events while the L1 solution produced 95 coefficients above the prototype nonzero threshold; exact event recovery is not guaranteed by the convex L1 model.

## Real-audio prefixes

Only the first 4,096 samples from each WAV were used. The stereo sample was averaged to mono for this single-channel experiment. The dictionary was initialized from patches in the same segment, and FISTA was capped at 300 iterations without satisfying its stopping criterion.

| Prefix | Dictionary | Atom count | Filter values | SNR |
|---|---|---:|---:|---:|
| 48 kHz mono | Multi-scale 16/32/64 | 6 | 224 | 19.372 dB |
| 48 kHz mono | Single-scale 32 | 7 | 224 | 23.953 dB |
| 44.1 kHz stereo-to-mono | Multi-scale 16/32/64 | 6 | 224 | 20.004 dB |
| 44.1 kHz stereo-to-mono | Single-scale 32 | 7 | 224 | 23.623 dB |

The simple multi-scale patch initializer underperformed the equal-filter-parameter single-scale baseline on these two short prefixes. This is a warning against assuming that multiple scales automatically improve fit; it is not a fair test of fully learned multi-scale CDL because the dictionary filters were not learned jointly with the coefficients, and the solver was not converged on these real-audio snippets.

## Test suite

`python -m unittest discover -s tests -v` — 57/57 passed for the complete KRM suite, including 12 time-domain CSC-specific tests. `python -m compileall -q krm_proto krm_td_csc tests benchmarks` also passed.

Coverage includes multi-scale atom normalization, direct operator boundary rules, adjoint identity, finite-difference gradient validation, FISTA monotonic objective descent, ADMM convergence, objective agreement between solvers, and a static check that the research solver modules do not call FFT/STFT/DCT functions.
