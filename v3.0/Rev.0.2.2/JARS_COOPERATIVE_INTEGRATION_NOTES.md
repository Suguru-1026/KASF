# JARS Cooperative Integration — KASF v3.0 Rev.0.2.2

Status: **experimental development implementation**. JARS remains an explicit experimental feature and is not promoted to standard/default status.

## Previous behavior

The `jars` experiment mode ran Kalman gap recovery first and then ran HPSS recovery. The second stage therefore observed components committed by the first stage; the two cue sources were not collected and evaluated as one cooperative candidate set.

## New cooperative path

The `jars` mode now uses `jarsRecover`:

1. For each selected frame, Kalman gap discovery reads the current encoded frame sequence and returns gap cues. Discovery does not mutate encoded frames.
2. HPSS analyzes the source neighborhood and classifies the frame as attack/percussive-like or harmonic/tail-like.
3. Initial Reader residual peaks, HPSS dominant peaks (for attack-like frames), and Kalman gap frequencies are merged into a frequency-deduplicated proposal set.
4. Candidate proposals are ranked by cue strength. The existing per-frame candidate limits remain conservative: up to three additions for attack-like frames and one for other frames.
5. For **each** candidate, the current component list is re-synthesized through the quantized KASF Reader. The residual is recalculated from that current baseline, then the candidate is proposed and checked by `jointGate`.
6. `jointGate` requires the exact local waveform/envelope gate and finite multi-resolution spectral metrics. Attack-like frames also retain the secondary-percussion envelope guard.
7. Only accepted candidates are appended. The next candidate is re-rendered against this updated component list, so it cannot rely on a stale baseline.

Kalman-derived accepted candidates are attributed in `kalman.recovered`; cooperative totals and cue counts are returned in `hpss` and `jars` stats. The worker report now labels the `jars` result as cooperative rather than implying two sequential independent recovery passes.

## Compatibility / scope

- `hpss` mode remains the standalone HPSS path.
- `kalman` mode remains the standalone Kalman recovery path.
- `off` remains a no-op.
- `jars` is still selected explicitly by the existing experiment-mode control. It is not automatically enabled.
- KASF v1 serialization, Reader v1.2, component quantization, storage modes, KCP behavior, worker layout, and embedded WASM payload are unchanged by this patch.
- The existing JARS exact-reader and spectral gate is reused; this patch changes candidate orchestration, not the wire format or synthesis model.

## Tests and validation

Added `tests/test-jars-cooperative.cjs`. It verifies:

- Kalman cue discovery happens before any cooperative candidate is committed.
- A Kalman cue can be merged with other cues and attributed when its candidate is accepted.
- The attack-frame candidate budget can admit multiple cooperative candidates.
- The Reader reconstruction passed to each later candidate gate includes earlier accepted candidates (`0`, then `0.1`, then `0.2` in the deterministic fixture).

Validation performed against the packaged KASF v3.0 Rev.0.2.2 HTML:

- All 29 deterministic `test-*.cjs` files passed individually, including the new cooperative JARS test. `test-short-approx-stress.cjs` was excluded because it is the long-running stress test.
- `bash build-validate.sh` passed; the embedded WASM remained 17,706 bytes with SHA-256 `2a7724def5d3026d08d03a5c0fc0e958d9c627e1266f60e62e35dd06431d4bd4`.
- HTML executable-script syntax check passed (6 script blocks).

Not performed: real-music listening comparison, full encode/decode on a Chromebook, browser `file://` E2E run, long-running stress test, or Emscripten production build. Therefore no audio-quality improvement or performance improvement is claimed. JARS remains experimental pending those checks.
