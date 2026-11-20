# TEST RESULTS — Rev0.9.19

## Summary

- HTML executable script syntax: PASS (6 executable script blocks parsed).
- New Worker/channel merge test: PASS.
- New Worker edge-case test: PASS.
- Existing Rev0.9.18 regression set: 23 of 24 test scripts completed successfully in the current validation session. The long `test-short-approx-stress.cjs` run exceeded the 240-second execution window and did not complete; this is a timeout/incomplete test, not a reported assertion failure.
- Chromium E2E smoke tests: PASS for synthetic Mono and Stereo WAVs, both whole-chunk and multi-chunk operation. No page errors or console errors were observed.
- KASF v1 structural checks: PASS for all four generated smoke outputs; header fields, frame count, channel count, frame body lengths and total body length parsed consistently.

## New architecture tests

### `test-three-worker-merge.cjs`

Validated guarded subrange output trimming, Mono body concatenation, Stereo [left,right] reconstruction when source bodies arrive in [right,left] order, and rejection of incomplete channel mappings.

### `test-three-worker-edgecases.cjs`

Validated 45 Mono split plans across 3 sample rates (44.1, 48 and 96 kHz) and 5 frame lengths (5, 10, 20, 30 and 40ms); subrange PCM slicing equality against independently prepared ranges for 48kHz→44.1kHz and 96kHz→48kHz, with linear and coherent sinc resampling; 5-channel ordering; internal Mono phase seam matching/adjustment; and malformed mapping rejection.

## Existing regression tests completed

The following 23 scripts completed successfully in the current validation session (some were rerun individually after broad-run timeout):

- `test-dpss-toeplitz.cjs`
- `test-dpss-wasm.cjs`
- `test-gpo-wasm.cjs`
- `test-html-script-syntax.cjs`
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

`test-short-approx-stress.cjs` did not finish within the 240-second execution window. The result is classified as NOT COMPLETED, not PASS and not FAIL.

## Chromium E2E smoke tests

Chromium was run in the available browser test environment using the HTML loaded into the page and synthetic WAV files provided through the file input. Blob Workers were used by the application. These were end-to-end generation runs, not isolated unit tests.

| Input | Mode | KASF channels | Frames | KASF bytes | Chunks | Result |
|---|---|---:|---:|---:|---:|---|
| 2.4s Mono | whole chunk | 1 | 239 | 11,304 | 1 | PASS |
| 2.4s Stereo | whole chunk | 2 | 239 | 19,996 | 1 | PASS |
| 6.2s Mono | 5s chunking | 1 | 619 | 34,660 | 2 | PASS |
| 6.2s Stereo | 5s chunking | 2 | 619 | 69,312 | 2 | PASS |

All four produced files were parsed through the KASF v1 structural parser, with no missing or trailing frame/channel payload data. No page/console errors were observed.

## Validation limits

- These browser runs used synthetic test audio, not a real music recording or a subjective listening comparison.
- The environment blocked direct `file://` navigation with an administrator restriction, so these runs validate Blob Worker execution in Chromium but do not validate the exact user's local-file launch conditions.
- No test was run on the user's Chromebook or other target PC.
- No end-to-end timing comparison against Rev0.9.18 was completed. This release must not yet be described as faster overall.
- Stereo output is not expected to be bit-identical to Rev0.9.18 because the two channels now run independent encoder/VP paths.
