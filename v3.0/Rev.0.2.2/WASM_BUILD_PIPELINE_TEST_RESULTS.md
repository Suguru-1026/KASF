# WASM Build Pipeline Repair — Test Results

Date: 2026-11-20

## Changes

- Corrected the default build target from the absent Rev0.9.16 comparison HTML to the primary Rev0.9.20 Temporal Guards HTML.
- Added explicit `KASF_HTML` and `KASF_WASM_OUT` overrides and early target-file validation.
- Made WASM embedding atomic and added a non-mutating `--check` mode.
- Added `tests/test-wasm-build-pipeline.cjs` for target routing, embedded-payload identity, and mismatch detection.

## Results

- `bash build-validate.sh`: PASS.
- Clang WASM output: 17,706 bytes.
- SHA-256: `2a7724def5d3026d08d03a5c0fc0e958d9c627e1266f60e62e35dd06431d4bd4`.
- Primary HTML embedded payload verification: PASS, byte-identical.
- `tests/test-wasm-build-pipeline.cjs`: PASS.
- Existing deterministic suite: 26 of 27 test scripts passed. `test-short-approx-stress.cjs` did not complete within the 300-second execution window; this is NOT COMPLETED, not PASS or FAIL.
- Historical note: the original pipeline validation used the then-primary Rev0.9.20 HTML path. The current v3.0 Rev.0.2.2 build scripts and tests now target `KASF-v3.0-Rev0.2.2.html`.
- Emscripten build was not executed because `em++` is unavailable in this environment.

## Scope boundaries

This is a build-pipeline repair only. It does not change the WASM C++ algorithms, KASF v1 serialization, Reader v1.2 synthesis, encoder search budgets, JARS, or KASE-2.1 behavior. No perceptual audio-quality improvement is claimed.
