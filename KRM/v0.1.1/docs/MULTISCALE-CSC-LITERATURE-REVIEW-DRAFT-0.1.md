# Multi-scale Convolutional Sparse Coding — Literature Review Draft 0.1

## 1. The important distinction

Convolutional sparse coding is a waveform/signal synthesis model:

```
x ~= sum_k d_k * a_k
```

The filters `d_k` are finite-support patterns, and `a_k` are their activation sequences. The model is shift-invariant: the same pattern can occur at different positions. The model itself does not require that `d_k` be a sinusoid, a frequency bin, or a spectral template.

Some high-performance solvers use the convolution theorem and FFTs as an internal numerical technique. That does not mean their output representation is a frequency-domain signal. The Draft 0.1 reference solver deliberately avoids FFTs to make the finite time-domain operator and its adjoint transparent.

## 2. Audio-specific evidence

Jao, Su, Yang, and Wohlberg (2016), *Monaural Music Source Separation Using Convolutional Sparse Coding*, explicitly model a monaural audio mixture as a sum of convolutions between estimated activations and prelearned dictionary filters, directly approximating the audio mixture in the time domain. Their broader evaluation found that the approach remained effective with a larger dictionary, but without score information and with a small dictionary it was not necessarily better than NMF. This is directly relevant: audio CSC is established, but dictionary coverage and prior information matter.

Jao, Yang, and Wohlberg (2015), *Informed Monaural Source Separation of Music based on Convolutional Sparse Coding*, also use a direct time-domain CSC model. The experiment is score-informed, so it is evidence for the representation, not a guarantee of blind general-purpose reconstruction quality.

## 3. Optimization and dictionary learning

Wohlberg (2016), *Efficient Algorithms for Convolutional Sparse Representations*, develops efficient algorithms for the globally optimized convolutional sparse representation problem and its dictionary-learning extension. The paper frames the objective as data fidelity plus a sparsity-inducing penalty.

Veshki and Vorobyov (2022), *Efficient ADMM-Based Algorithms for Convolutional Sparse Coding*, develop improved ADMM solutions to the convolutional least-squares subproblem, dictionary-learning algorithms, and an error-constrained CSC variant. Their public companion repository contains a multi-scale convolutional dictionary-learning implementation. The reported examples and repository training data are image-oriented; they demonstrate algorithmic multi-scale CDL, not audio superiority.

The companion implementation's multiscale CDL alternates a CSC update with a dictionary update and imposes scale-specific filter support constraints. This is a more complete formulation than the current KRM TD-CSC initializer, which only selects waveform patches and then optimizes activations with a fixed dictionary. Garcia-Cardona and Wohlberg's comparative review also notes that dictionary-learning methods can differ substantially in performance; selecting a solver by name alone is not enough.

An online direction is also relevant for long recordings. Wang et al. (ICML 2018) propose sample-dependent dictionaries formed as linear combinations of a smaller set of learned base filters, with online learning intended to reduce time and space costs. This is a scalability idea to investigate, not an audio-specific quality result.

## 4. Audio dictionary design is not solved by CSC itself

Audio work illustrates both the potential and the assumptions. Jao et al. model a mixture directly in time using convolutions of activation sequences with pre-learned audio filters. A separate piano-transcription model uses recorded waveform templates for individual pitches and estimates activation sequences. The authors describe a context-dependent setting in which templates are recorded for the specific piano and environment. Such a design can be powerful when the dictionary matches the target instrument and performance conditions, but it also makes those conditions part of the model. A later extension adds lateral-inhibition constraints and multiple templates per pitch by truncating long waveforms to different durations, explicitly addressing note-length variation. A general-purpose music representation cannot rely on a single fixed waveform per note without studying these variations.

The dictionary must cover transient attacks, decays, timbral variation, pitch/dynamic changes, and potentially non-pitched sound. Too many highly similar filters can also create ambiguity and cost. Dictionary pruning and redundancy control therefore deserve explicit experiments.

## 5. Boundary conditions

Wohlberg (2016), *Boundary Handling for Convolutional Sparse Representations*, explicitly studies boundary artifacts arising from periodic boundary conditions in frequency-domain CSC solvers. This supports treating boundary policy as part of the mathematical model, not an implementation detail.

Draft 0.1 uses finite linear convolution with explicit full-overlap coefficient maps and zero extension outside the observed sample interval. It does not wrap the end of the waveform back to its beginning. The forward and adjoint operators are tested as a matched pair.

## 6. Useful objective variants

The basic CBPDN model is

```
min_a 0.5 ||sum_k d_k * a_k - x||_2^2 + lambda ||a||_1
```

Research tools such as SPORCO document useful variants:

- Joint multi-channel sparsity (`ell2,1`) for activation structures shared across channels.
- Gradient regularization of activation maps, which can promote temporal smoothness.
- An explicit error-bound form `min ||a||_1 subject to ||sum_k d_k * a_k - x||_2 <= epsilon`.

The variants should not be combined automatically. For example, a smooth activation penalty may help a sustained waveform pattern but can smear impulsive events.

## 7. References

1. B. Wohlberg, “Efficient Algorithms for Convolutional Sparse Representations,” *IEEE Transactions on Image Processing*, 25(1), 301–315, 2016. DOI: https://doi.org/10.1109/TIP.2015.2495260
2. B. Wohlberg, “Boundary Handling for Convolutional Sparse Representations,” ICIP 2016, pp. 1833–1837. DOI: https://doi.org/10.1109/ICIP.2016.7532675
3. F. Veshki and S. Vorobyov, “Efficient ADMM-Based Algorithms for Convolutional Sparse Coding,” *IEEE Signal Processing Letters*, 29, 389–393, 2022. DOI: https://doi.org/10.1109/LSP.2021.3135196
4. P.-K. Jao, L. Su, Y.-H. Yang, and B. Wohlberg, “Monaural Music Source Separation Using Convolutional Sparse Coding,” *IEEE/ACM Transactions on Audio, Speech, and Language Processing*, 24(11), 2158–2170, 2016. DOI: https://doi.org/10.1109/TASLP.2016.2598323
5. P.-K. Jao, Y.-H. Yang, and B. Wohlberg, “Informed Monaural Source Separation of Music based on Convolutional Sparse Coding,” ICASSP 2015, pp. 236–240. DOI: https://doi.org/10.1109/ICASSP.2015.7177967
6. SPORCO documentation, convolutional BPDN variants: https://sporco.readthedocs.io/en/latest/invprob/cbpdn.html
7. Veshki & Vorobyov companion code (multi-scale CDL reference): https://github.com/FarshadGVeshki/Convolutional-Sparse-Coding
