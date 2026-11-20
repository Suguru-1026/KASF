# Convolutional Dictionary Learning — Research Draft 0.2

Date: 2026-11-14  
Scope: independent time-domain waveform model; no KASF format constraint.

## 1. Research objective

The target is a waveform-domain representation. Frequency-domain translation is a possible interoperability layer only after the underlying algorithm becomes mature. The current experiments do not use FFT, STFT, DCT, spectral bins, or sinusoidal component lists.

## 2. Joint objective

For training waveforms \(x^{(s)}\), waveform atoms \(d_k\), and activation maps \(a_k^{(s)}\),

\[
\min_{D,\{a^{(s)}\}}
\frac12\sum_s\left\|\sum_k d_k * a_k^{(s)}-x^{(s)}\right\|_2^2
+\lambda\sum_{s,k}\|a_k^{(s)}\|_1
\]

subject to

\[
\|d_k\|_2=1\quad\forall k.
\]

The atom norm constraint removes the trivial scale ambiguity between an atom and its activation map. It does not remove permutation/sign ambiguities, correlated-atom ambiguity, or the existence of different dictionaries that produce similar waveforms.

The problem is non-convex jointly in \(D\) and \(a\). With the dictionary fixed, the coefficient subproblem is convex. With coefficient maps fixed, the dictionary subproblem is a smooth least-squares problem over a product of unit spheres.

## 3. Draft 0.8 algorithm

### 3.1 Sparse-coding update

For each training example, solve the CBPDN coefficient problem with monotone backtracking FISTA. Existing coefficients are used as a warm start. The Lipschitz estimate depends on the current dictionary and signal length, not signal content; it is therefore cached once per distinct signal length per outer iteration and shared across the training examples of that length.

The solver now reports the proximal-gradient mapping norm

\[
G_L(a)=L\left(a-\operatorname{soft}(a-L^{-1}A_D^*(A_D(a)-x),\lambda/L)\right).
\]

A small coefficient-step norm alone is not enough to report convergence. When the iterate step is small, the solver additionally checks the proximal-gradient mapping against the configured tolerance. `optimality_residual` records the final absolute mapping norm. The outer CDL loop reports convergence only if its dictionary objective/step criteria are met and every coefficient solve in that final outer iteration also reports convergence. It is an approximate KKT/stationarity diagnostic for the convex fixed-dictionary subproblem, not a global certificate for the non-convex CDL problem.

### 3.2 Dictionary gradient

Let

\[
r^{(s)}=A_D(a^{(s)})-x^{(s)}.
\]

Under the finite full-overlap convention used by `operators.py`, for an atom of length \(L_k\),

\[
\frac{\partial f}{\partial d_k[j]}=
\sum_s\sum_{n=0}^{N_s-1}
 r^{(s)}[n] a_k^{(s)}[n+L_k-1-j].
\]

This exact time-domain formula is implemented in `krm_td_csc/learning.py` and checked against central finite differences. No dense Toeplitz matrix is constructed.

### 3.3 Unit-sphere update

The Euclidean gradient is projected onto the tangent space of the unit sphere:

\[
g_k^{\mathrm{tan}}=g_k-(d_k^Tg_k)d_k.
\]

A candidate is formed by

\[
\tilde d_k=d_k-\eta g_k^{\mathrm{tan}},\qquad
 d_k^{new}=\tilde d_k/\|\tilde d_k\|_2.
\]

The shared step is reduced by backtracking until an Armijo sufficient-decrease condition is met for the smooth reconstruction loss with activation maps held fixed. If no candidate passes the configured backtracking budget, the dictionary is unchanged for that outer iteration.

The activation update is monotone for its current fixed dictionary due to the monotone FISTA implementation; dictionary update is accepted only with a sufficient-decrease test. The total penalized objective is checked for non-increase after each outer iteration.

## 4. Current benchmark protocol

`benchmarks/run_dictionary_learning.py` reads PCM WAVs, applies one global peak scaling to 0.75, and splits time-distributed non-overlapping windows into train and validation groups using a fixed seed. For stereo files, the left and right channels become separate examples that share a dictionary but have independent activation maps. This is not joint stereo modelling.

The initial dictionary is selected only from training windows. Validation windows are not used for patch selection, dictionary updates, or lambda calculation. The same lambda and FISTA iteration cap are used for the initial and learned dictionaries.

These are small held-out time-window experiments from two pre-existing Library WAVs, not broad generalisation tests. The source WAVs are not modified.

## 5. Results

### 5.1 Validation results, atom length 24 / segment length 512

| Source | Initial SNR | Learned SNR | Change | Initial relative L2 | Learned relative L2 |
|---|---:|---:|---:|---:|---:|
| 48 kHz mono | 13.540 dB | 13.667 dB | +0.127 dB | 0.21037 | 0.20733 |
| 44.1 kHz stereo, channel examples | 17.988 dB | 20.322 dB | +2.334 dB | 0.12606 | 0.09636 |

### 5.2 Validation results, atom length 64 / segment length 1024

| Source | Initial SNR | Learned SNR | Change | Initial relative L2 | Learned relative L2 |
|---|---:|---:|---:|---:|---:|
| 48 kHz mono | 10.874 dB | 11.909 dB | +1.035 dB | 0.28596 | 0.25382 |
| 44.1 kHz stereo, channel examples | 14.335 dB | 16.472 dB | +2.137 dB | 0.19197 | 0.15010 |

### 5.3 Same 2048-sample segments and 384 filter parameters

For the 44.1 kHz stereo source, a 64-sample/6-atom dictionary and a 128-sample/3-atom dictionary each have 384 filter parameters.

| Atom length / count | Initial validation SNR | Learned validation SNR | Initial relative L2 | Learned relative L2 |
|---|---:|---:|---:|---:|
| 64 / 6 | 10.087 dB | 10.403 dB | 0.31308 | 0.30189 |
| 128 / 3 | 6.556 dB | 7.747 dB | 0.47009 | 0.40985 |

This particular split favoured the shorter 64-sample atoms. It does not prove that shorter atoms are generally better: the models differ in atom count, initialisation, and non-convex training path, and the sparse-coding runs were capped at only 35 iterations without convergence.

### 5.4 Interpretation and limits

- Dictionary learning improved validation SNR in all listed small experiments, but the gain varied from very small to around 2.3 dB.
- The results are encouraging but not a claim of state-of-the-art waveform fidelity.
- Some FISTA coefficient subproblems hit their iteration caps. The per-example `coding_converged_count` and `optimality_residual` must be read alongside SNR.
- The training objective decreased monotonically in the reported CDL runs. This is a property of the accepted block updates, not proof of a global minimizer.
- The initial dictionary and the learned dictionary can be permutation/sign ambiguous; same-index atom cosine is only a rough diagnostic.
- Execution times belong to the current development runtime, not the user's Chromebook or parent PC.

## 6. Literature and algorithmic alternatives

1. **Audio-domain CSC:** Jao et al. model a monaural music mixture directly as a sum of convolutions between temporal dictionary filters and activations, rather than estimating a magnitude spectrogram. This supports CSC as an audio waveform model, while also showing that the training dictionary and application assumptions matter.
2. **Joint/direct dictionary optimization:** published work explores updating coefficients and dictionary jointly rather than using only conventional alternating steps. It is a possible future comparator, but its objective and convergence conditions need a careful implementation audit before adoption.
3. **Online CDL:** online algorithms reduce the need to keep all training examples in memory. Some efficient formulations use frequency-domain algebra internally; they can still represent a time-domain convolutional model, but are not used in this current direct-time reference engine.
4. **Slice-based / LoBCoD-style methods:** local non-overlapping coefficient slices allow time-domain convolutional coding and dictionary updates without forming a global dense convolution matrix. This is a major next candidate for long recordings and memory use.
5. **Error-constrained CSC:** instead of choosing \(\lambda\), solve a sparse representation problem under an explicit residual norm bound \(\epsilon\). This aligns more directly with a target fidelity specification and should be compared after the dictionary-learning baseline is stable.

## 7. Next algorithmic steps

1. Implement and compare slice-based local block coordinate descent (SBDL/LoBCoD-style) against global FISTA under the same time-domain operator and boundary convention.
2. Implement error-constrained CBPDN and report the achieved residual norm against a requested \(\epsilon\).
3. Add dead-atom detection and controlled reinitialisation, with tests proving the objective does not increase after acceptance.
4. Add coherence diagnostics and optional redundancy control; do not force orthogonality if it damages waveform fit.
5. Expand training/validation windows and use multiple tracks / different source types, not only two short WAVs.
6. Study longer atom lengths and true multi-scale CDL after a solver can converge at comparable tolerances.
7. Introduce stereo joint constraints only after the single-channel/shared-dictionary baseline is stable.
8. Only after the waveform model is mature, study translation to KASF frequency information.

## 8. References

- P.-K. Jao, L. Su, Y.-H. Yang, and B. Wohlberg, “Monaural Music Source Separation Using Convolutional Sparse Coding,” *IEEE/ACM Transactions on Audio, Speech, and Language Processing*, 24(11), 2158–2170, 2016. DOI: https://doi.org/10.1109/TASLP.2016.2598323
- B. Wohlberg, “Convolutional Dictionary Learning: A Comparative Review and New Algorithms,” *IEEE Transactions on Image Processing*, 27(10), 5132–5145, 2018. IEEE Xplore: https://ieeexplore.ieee.org/document/8364626/
- J. Liu, C. Garcia-Cardona, B. Wohlberg, and W. Yin, “First- and Second-Order Methods for Online Convolutional Dictionary Learning,” *SIAM Journal on Imaging Sciences*, 11(2), 1589–1628, 2018. DOI: https://doi.org/10.1137/17M1145689
- Y. Zeng, J. Chen, and G.-B. Huang, “Slice-Based Online Convolutional Dictionary Learning,” *IEEE Transactions on Cybernetics*, 51(10), 5116–5129, 2021. DOI: https://doi.org/10.1109/TCYB.2019.2931914
- F. Veshki and S. A. Vorobyov, “Efficient ADMM-Based Algorithms for Convolutional Sparse Coding,” *IEEE Signal Processing Letters*, 29, 389–393, 2022. DOI: https://doi.org/10.1109/LSP.2021.3135196
- “Proximal Gradient Nonconvex Optimization Algorithm for the Slice-Based ℓ0-Constrained Convolutional Dictionary Learning,” *Knowledge-Based Systems*, 2023. https://www.sciencedirect.com/science/article/abs/pii/S0950705122012813
- “Joint and Direct Optimization for Dictionary Learning in Convolutional Sparse Representation,” 2019. https://pubmed.ncbi.nlm.nih.gov/31021776/
