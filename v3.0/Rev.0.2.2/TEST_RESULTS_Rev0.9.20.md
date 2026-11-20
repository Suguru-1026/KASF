# TEST RESULTS — Rev0.9.20 Temporal Guards

## Summary

- New temporal-guard unit tests: **PASS**.
- HTML executable-script syntax: **PASS** (6 executable script blocks parsed).
- Three-Worker merge and edge-case tests: **PASS**.
- Inherited Rev0.9.19/0.9.18 regression scripts: **PASS** for every script executed in this validation pass.
- Overall: **26 test scripts passed; 1 long-duration stress script was not completed in this pass**.
- KASF v1 format and Reader v1.2 implementation were not changed by this revision.
- No claim is made that real-music sound quality has improved: real-song listening and controlled audio A/B comparison remain outstanding.

## Rev0.9.20-specific tests

### `tests/test-temporal-guards.cjs` — PASS

Validated:

- Conservative phase-innovation threshold and cap.
- Attack and unstable-track bypass; OFF mode no-op.
- Safe handling of invalid/zero hop duration in the attack mask.
- Detection and correction of a synthetic one-frame phase spike with opposing adjacent phase residuals.
- Preservation of attack-adjacent phase spikes.
- Detection and soft attenuation of a weak, isolated, non-harmonic component.
- Conservative attenuation cap (18%) and Balanced attenuation cap (30%), with Balanced stronger than Conservative for the fixture.
- Harmonic and persistent-component protection.
- No component deletion.

This is a deterministic algorithm/unit fixture, not a perceptual listening test.

## Worker / format regression tests

### `test-html-script-syntax.cjs` — PASS

All 6 executable script blocks parsed successfully.

### `test-three-worker-merge.cjs` — PASS

Validated guarded subrange trimming, Mono body concatenation, Stereo channel-order restoration and malformed/incomplete mapping rejection (1,600-frame fixture).

### `test-three-worker-edgecases.cjs` — PASS

Validated 45 Mono split cases across 3 sample rates and 5 frame lengths, 5-channel ordering, internal Mono phase seam and malformed mappings.

## Inherited regression tests — PASS

The following 23 inherited scripts completed successfully:

- `test-dpss-toeplitz.cjs`
- `test-dpss-wasm.cjs`
- `test-gpo-wasm.cjs`
- `test-hybrid-extreme-equivalence.cjs`
- `test-hybrid-optimized-equivalence.cjs`
- `test-metric-reader-equivalence.cjs`
- `test-nomp-direct-workspace.cjs`
- `test-qrp-wasm.cjs`
- `test-reader-workspace.cjs`
- `test-selected-restore.cjs`
- `test-short-approx-highfreq.cjs`
- `test-short-approx-reader.cjs`
- `test-short-approx-region-gate.cjs`
- `test-vp-cache-equivalence.cjs`
- `test-vp-column-workspace.cjs`
- `test-wasm-bootstrap.cjs`
- `test-wasm-fft-adapter.cjs`
- `test-wasm-fft.cjs`
- `test-wasm-inplace-qr.cjs`
- `test-wavelet-wasm.cjs`
- `test-worker-fft-route.cjs`
- `test-workspace.cjs`
- `test-html-script-syntax.cjs`

Notable equivalence checks: Hybrid Optimized and Extreme outputs matched their existing expected outputs exactly; Reader/metric equivalence fixtures were bit-identical; FFT fixtures were bit-identical; WASM/JS QRP, DPSS, GPO and NOMP fixtures passed their respective equivalence checks.

`test-short-approx-stress.cjs` was **not completed in this Rev0.9.20 pass**. The Rev0.9.19 validation report records that this long-running test exceeded a 240-second execution window. It is classified as NOT COMPLETED, not PASS and not FAIL.

## Browser / real-audio validation limits

- A Rev0.9.20 Chromium end-to-end encode was not completed in this pass. A headless browser startup attempt timed out during the container's DBus/browser startup; this is not treated as an application test result.
- The previous Rev0.9.19 Chromium synthetic Mono/Stereo smoke tests do not constitute a Rev0.9.20 end-to-end test.
- No real music file was encoded and auditioned specifically to assess the new guards.
- No A/B measurement of musical-noise audibility, phase discontinuity rate, transient fidelity, or spectral error was completed.
- No target Chromebook/PC validation or Rev0.9.18-to-Rev0.9.20 end-to-end timing comparison was completed.

## Interpretation

The automated tests support that the new guards' designed branches operate and that selected inherited numerical, Reader, WASM and three-Worker pathways continue to pass. They do not establish perceptual improvement. The Conservative settings are defaults for cautious evaluation, not a guarantee that every legitimate weak partial is preserved. For real-source assessment, compare both guards OFF versus Conservative, then evaluate Balanced separately; retain the OFF path as a regression control.
