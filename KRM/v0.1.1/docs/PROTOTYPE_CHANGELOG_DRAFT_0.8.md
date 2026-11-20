# Changelog

## 0.8.0 — 2026-11-14

- Added alternating direct-time-domain Convolutional Dictionary Learning (CDL) for multiple training signals with shared unit-norm waveform atoms and independent activation maps.
- Added exact finite-convolution dictionary gradients, tangent-space projection on unit spheres, and Armijo backtracking for accepted atom updates.
- Added FISTA warm-start support and cached Lipschitz estimates per signal length within each dictionary-learning outer iteration.
- Added a proximal-gradient mapping residual check before FISTA reports convergence; exposed the final optimality residual in solver results.
- Added train/held-out-validation WAV benchmark protocol. Stereo channels are independent examples sharing one dictionary; no joint stereo coupling is claimed.
- Added 24/64/128-sample atom comparisons, training/validation metrics, dictionary coherence diagnostics, and a Japanese CDL research note.
- Kept all time-domain CSC/CDL reference operators and solvers free of FFT/STFT/DCT calls. KASF/KRC/KRM-IF integration remains deferred.
- Full test suite now has 66 passing tests.

## 0.7.0 — 2026-11-14

- Added an independent `krm_td_csc` research package for multi-scale time-domain convolutional sparse coding; frequency-domain translation is explicitly deferred.
- Added finite full-overlap linear convolution operators with per-atom coefficient-map lengths and tested exact adjoints / finite-difference gradients.
- Added monotone backtracking FISTA and direct-time-domain ADMM with matrix-free conjugate gradients for CBPDN.
- Added deterministic waveform-patch dictionary initialization; explicitly documented that this is an initializer, not convolutional dictionary learning.
- Added synthetic and two short real-WAV exploratory benchmarks, including an equal-filter-parameter single-scale baseline.
- Added Japanese research notes and literature review covering audio CSC, multi-scale dictionary learning, solver choices, and boundary handling.
- Kept `krm_proto`'s standard-library-only dependency profile; NumPy is an optional `research` extra.
- Full test suite now has 57 passing tests.

## 0.6.0 — 2026-11-14

- Added channel-local temporal component association to the C++ FastGen baseline using predicted frequency, phase advance, and amplitude continuity.
- Added KASF-TrackMap-JSONL-v1 sidecar with per-frame/channel track IDs aligned to KASF component order; added SHA-256 and row-count metadata.
- Kept tracking metadata-only by default. Regression test proves tracking-on and tracking-off produce byte-identical KASF and Base WAV files.
- Added opt-in experimental phase-derived frequency refinement with symmetric-window phase-center compensation; documented it as non-default because synthetic tests showed Base SNR regressions in several cases.
- Exposed `--no-tracking` and `--experimental-track-refine` through Python APIs and both CLIs.
- Added optional Hungarian global minimum-cost assignment alongside the default greedy matcher.
- Added deterministic assignment tests, CLI/API selection, and full bridge support for Hungarian tracking.
- Benchmarked greedy vs Hungarian on two real Library WAV samples; Hungarian modestly reduced track fragmentation while increasing compute time, so greedy remains the default.
- Test suite now has 45 tests.

## 0.5.0 — 2026-11-14

- Added native C++17 KASF v1 FastGen baseline encoder with bounded-window WAV input, periodic-Hann FFT peak analysis, sub-bin peak interpolation, weighted sine/cosine fitting, and quantized residual pursuit.
- Added native local-Reader OLA Base WAV generation using the final quantized KASF components.
- Updated the FastGen → Reader Base → KRC bridge to use native Base rendering instead of the slower Python per-sample reference renderer.
- Retained Python OLA rendering for differential/reference testing.
- Corrected KASF magic from prototype typo `KFSA` to source-confirmed `KASF`.
- Improved peak search to skip out-of-band bins instead of terminating when an excluded frequency dominates.
- Added optional half-hop phase-shifted boundary guard frames.
- Added Base-provenance hashes and explicit KRM-PROTO-PCM-Q-v1 metadata.
- Added `bridge-fast --resume`, which validates and reuses the existing KASF/Base files before resuming KRC journal capture.
- Added automated parity tests across PCM 8/16/24/32, low-frequency exclusion, native/Python Base equality, and complete KRC restore.
- Updated README and Draft 0.5 Reader/metadata/FastGen contracts.

## 0.4.0 — 2026-11-14

- Added strict KASF v1 header/body decoder for the audited 32-byte header and 6-byte components.
- Added bounded-memory, channel-planar float64 OLA renderer matching the audited KASF05_Reader local synthesis equation.
- Added explicit sample-rate/sample-count side metadata requirements and rejection of uncovered timelines/trailing bytes.
- Corrected the Draft 0.3 interpretation: a final global peak-normalized Reader PCM export is not established by the audited Rev.0.9.20 source.
- Added KRM-IF logical metadata contract Draft 0.4.

## 0.3.0

- Added resumable KRC capture and source-audited KASF adapter contract.

## 0.2.0

- Added direct synchronized chunk capture, stricter KRM-IF validation, streaming analysis and predictor checks, KRM-FC frame proposals, and raw PCM restore.
