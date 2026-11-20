# KRM Time-Domain CSC Research — Draft 0.1

## Research target

The current objective is to discover a high-fidelity waveform representation. Translation to KASF frequency components is deferred and is not a design constraint for this research engine.

The research model must represent the observed PCM waveform directly. It must not require an STFT, spectrogram, sinusoidal component list, or frequency-bin interpretation.

## Convolutional synthesis model

For a finite observed waveform `x` of `N` samples and `K` waveform atoms `d_k`, each atom has its own length `L_k`. Its activation map `a_k` has `N + L_k - 1` positions. Map index `t` represents an atom start at absolute sample `t - (L_k - 1)`. Thus all atom placements that overlap the observed signal are represented, including partial overlaps at either boundary.

The reconstructed signal is

```
y[n] = sum_k sum_j d_k[j] * a_k[n + (L_k - 1) - j]
     for 0 <= n < N
```

Equivalently, `y` is the sum of each full linear convolution cropped to `[L_k - 1 : L_k - 1 + N]`.

This is a finite, zero-extended linear-convolution model. It does not impose periodic wrap-around at the signal boundaries. It is not circular convolution.

## Sparse coding objective

The baseline Convolutional Basis Pursuit Denoising (CBPDN) problem is

```
min_a  0.5 * ||A(a) - x||_2^2 + lambda * sum_k ||a_k||_1
```

`A` is the multi-filter convolution operator. The first term rewards waveform fidelity; the second discourages a dense collection of activations. `lambda` controls the trade-off. A low value generally improves fit but activates more coefficients; a high value encourages sparsity but increases residual error.

This objective is a modelling choice, not a guarantee of the globally sparsest or physically meaningful decomposition. A highly coherent dictionary can admit multiple similar activation maps.

## Exact adjoint matters

Optimizers need the adjoint `A*`, not an approximate reverse operation. The implementation is tested against the inner-product identity

```
< A(a), r > = < a, A*(r) >
```

and a finite-difference gradient check. Full-overlap boundary handling is tested for atoms that start before sample zero and atoms that extend past the final sample.

## Solvers in Draft 0.1

### Monotone backtracking FISTA

FISTA solves the convex L1-regularized objective using a proximal-gradient update and soft thresholding. The Lipschitz estimate is initialized with power iteration. Backtracking enforces the smooth majorization condition. A monotone restart is used if an accelerated step increases the objective relative to the previous iterate.

This is a useful reference for convergence and objective comparisons. Its cost is dominated by repeated forward and adjoint convolutions.

### Direct-time-domain ADMM + matrix-free conjugate gradients

ADMM splits the coefficient variables with `a = z`:

```
a-update:  (A* A + rho I) a = A* x + rho (z - u)
z-update:  z = soft_threshold(a + u, lambda / rho)
u-update:  u = u + a - z
```

The `a`-update is solved using conjugate gradients (CG), applying `A* A + rho I` as an operator. No dense matrix is built. No FFT or frequency-domain transform is used. Adaptive `rho` balancing may be enabled; whenever `rho` changes, the scaled dual variable is rescaled to preserve the unscaled dual variable.

This solver is an algorithmic reference, not yet a long-file production implementation. Direct convolution and repeated CG products can be expensive.

## Multi-scale dictionary initialization

The current initializer samples waveform patches at several lengths (e.g. 16, 32, 64 samples), L2-normalizes them, and uses a farthest-point selection based on absolute mutual correlation to promote shape diversity.

Important distinction: this is **patch-based dictionary initialization**, not convolutional dictionary learning. The atoms are not yet learned jointly with activations. A multi-scale model is only as good as its dictionary and coding solver; the presence of several filter lengths does not inherently improve reconstruction.

## Current experimental findings

### Known-dictionary synthetic case

- 512 observed samples.
- Four atoms of lengths 12, 24, 48, 24.
- Sixteen planted nonzero activation events.
- `lambda = 0.002`.

The direct-time FISTA run converged in 1,096 iterations to objective 0.0155234979, SNR 39.831 dB, in 0.681 s in the current execution environment. The direct-time ADMM+CG run converged in 129 outer iterations (1,892 total CG iterations) to objective 0.0155562164, SNR 39.516 dB, in 0.813 s. The objective gap is about 3.3e-5, indicating that both solvers reached very similar solutions for this test case. These times are machine- and implementation-specific.

Although the synthetic source used 16 events, the L1 solution had 95 coefficients above the prototype nonzero threshold. This is a reminder that sparse convex coding does not guarantee recovery of the original event labels when atoms are correlated or the inverse problem is ambiguous. Waveform fit and event interpretability must be evaluated separately.

### Two short real-audio prefixes

Each test used only the first 4,096 samples of a PCM WAV. The second test had two channels, which were averaged to mono solely for this first single-channel experiment. Dictionary patches were drawn from the same signal segment being represented (in-sample initialization), not from an independent training set. The solver was capped at 300 FISTA iterations and had not met its stopping tolerance at the cap.

A multi-scale dictionary with two atoms at each length 16/32/64 (224 total filter coefficients) achieved 19.372 dB and 20.004 dB SNR on the two prefixes. A single-scale dictionary with seven 32-sample atoms (also 224 total filter coefficients) achieved 23.953 dB and 23.623 dB.

This is **not** evidence that multi-scale CSC is worse in general. It demonstrates that the current simple multi-scale patch initializer is not sufficient to make multi-scale coding better. The comparison is exploratory, short, in-sample, and not converged. Proper convolutional dictionary learning, larger and more representative training data, convergence to the same tolerance, and held-out evaluation remain necessary.

## Known limitations

- Single-channel solver only. Stereo is averaged to mono in the current real-audio benchmark.
- Fixed atoms after initialization; no learned-dictionary update yet.
- L1 regularization only; no explicit error-budget constraint yet.
- No group sparsity, channel coupling, temporal gradient regularization, or event-level prior yet.
- Direct time-domain convolutions are a reference implementation and are not expected to scale to long recordings without optimized kernels, block methods, or a faster linear solver.
- No KASF, KRC, or KRM-IF integration. This research package only produces a floating-point waveform approximation and diagnostics.

## Next research steps

1. Implement alternating convolutional dictionary learning (CDL) for one or several training signals. Keep filter normalization constraints explicit.
2. Compare penalized CBPDN against constrained error form `min ||a||_1 subject to ||A(a)-x||_2 <= epsilon`, so the target waveform error is user-specified.
3. Add multi-channel joint sparsity only after the mono solver is stable; compare shared and channel-specific activation maps.
4. Investigate temporal regularization per atom family. Smoothness can help sustained patterns but may smear attacks, so it must be tested rather than enabled globally.
5. Compare FISTA, direct ADMM+CG, greedy pursuit, and accelerated convolution implementations under the same objective, stopping criteria, and compute budget.
6. Test full-length speech/music, transients, low-level details, and boundary regions. Track L2, max error, local error, transient error, runtime, memory, and representation size.
7. Only after the waveform algorithm matures should a translation layer to KASF be designed.
