# CHANGELOG — KASF v3.0 Rev.0.2.2

## v3.0 Rev.0.2.2 — Added
- Stable-track phase innovation limiter in the live phase tracker, with attack/instability bypass.
- Final three-frame isolated phase-spike detector/corrector after PPR/GPO. It only corrects spikes with opposite adjacent residuals, rather than smoothing every phase transition.
- Temporal persistence-based Musical Noise Guard using one-to-one adjacent-frame frequency/amplitude matching.
- Soft attenuation of weak isolated non-harmonic components; no component deletion. Attack, abrupt-rise/transient, file-edge and harmonic protection; adjacent-frame persistence protection in Conservative mode.
- UI controls for Phase Jump Guard and Musical Noise Guard: OFF / Conservative / Balanced.
- Separate counters and output report fields for detected/limited phase jumps and musical-noise attenuation.
- Node tests for phase clamp, phase-spike detection, attack bypass, weak isolated component attenuation, harmonic protection and OFF no-op.

## v3.0 Rev.0.2.2 — Preserved
- Three-Worker A/B/C architecture and routing.
- KASF v1 32-byte header and 48-bit component representation.
- Reader v1.2 synthesis path, component frequency quantization and phase quantization.
- Existing VP/QR/Multi-start/KASE iteration budgets and candidate-generation paths.
- Final exact Reader evaluation inside existing optimizers.

## 継承機能の動作メモ
- New temporal guards default to Conservative, and can be independently switched OFF for A/B comparison.
- Phase jump limits apply only to stable, non-attack tracked components.
- Final phase-spike correction requires a one-frame outlier signature across three adjacent frames. Persistent phase steps are not force-smoothed.
- Musical Noise Guard attenuates but never deletes candidates; its maximum configured attenuation is 18% Conservative / 30% Balanced.
- The guards are heuristic. Real-music listening tests and controlled A/B measurement remain necessary.

## 2026-11-20 — Cooperative JARS development patch (experimental)

- Replaced the `jars` mode's sequential Kalman-then-HPSS execution with a cooperative candidate path that gathers residual, HPSS, and Kalman cues before committing candidates.
- Each candidate is re-evaluated against a fresh quantized Reader reconstruction that includes all previously accepted candidates in that frame.
- Retained the exact waveform/envelope + multi-resolution spectral gate and attack-frame secondary-percussion guard.
- Kept standalone `hpss`, `kalman`, and `off` modes unchanged. JARS remains an explicit experiment mode; it is not promoted to a default/standard feature.
- Added `tests/test-jars-cooperative.cjs` and `JARS_COOPERATIVE_INTEGRATION_NOTES.md`.
- Validation: 29 deterministic test files passed individually (excluding the long-running short-approx stress test); Clang WASM validation and embedded-payload verification passed. Real-audio listening, Chromebook/browser E2E, stress test, and Emscripten production build remain unperformed.


## Version / save-tag update

- Updated the product-facing version to KASF v3.0 Rev.0.2.2 across the primary HTML and current package documentation.
- Updated generated KASF, KCP, and JSON artifact filenames to use `v3-R0-2-2`.
- Added product version / revision / save-tag fields to new OPFS checkpoint metadata.
- Preserved KASF v1 serialization, Reader v1.2, KASF-KCP-1 format identification, and the existing OPFS directory so older data remains accessible.
