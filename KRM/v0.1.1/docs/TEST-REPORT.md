# KRM Prototype Draft 0.6 — Test Report

Date: 2026-11-14

## Automated tests

- `python -m unittest discover -s tests -v`: **45/45 passed**.
- `python -m compileall -q krm_proto tests examples benchmarks`: passed.
- Native C++ compile with GCC 14.2.0 and `-O3 -std=c++17 -ffp-contract=off -DNDEBUG -Wall -Wextra -Wpedantic -Werror`: passed with no warnings.
- Tests retain Draft 0.1/0.2 KRM-IF compatibility, resumable KRC, integrity validation, predictors, energy analysis, and exact integer PCM restoration.
- FastGen integration tests cover real KASF magic, tone recovery, output metadata, C++ Base vs Python reference parity, 8/16/24/32-bit Base PCM, odd 221/110 frame-hop geometry, out-of-band low-frequency exclusion, KRC interruption/resume without regenerating KASF/Base, and complete FastGen → Base → KRC → verify → restore operation.

## KASF v1 format correction

The user's Rev.0.9.20 `buildKASF()` source writes the four-byte magic `KASF`. Draft 0.4's Python decoder and one test fixture mistakenly expected `KFSA`, so the old prototype could reject real KASF files. Draft 0.5 now checks/writes `KASF`, and a negative test rejects the transposed `KFSA` magic.

## Actual Rev.0.9.20 Reader comparison

A Node.js harness (`tests/compare_reader_node.cjs`) extracts the actual `KASF05_Reader` source from the Library copy of `KASF-2.0-Evolution-Rev0.9.20-Temporal-Guards.html` (SHA-256 `5647bf57659862432f9e9d58bac6d9ad6bfcd976281b698a7b18dc2e662e73ee`), loads the KASF v1 file, and calls the actual `KASF05_Reader.render()` for both channels. It was compared with the Python float64 OLA renderer on a synthetic 10-second, 48 kHz stereo input:

- Guarded timeline: 480,480 samples/channel.
- Values compared: 960,960 float64 values.
- Maximum absolute difference: `2.220446049250313e-16`.
- Mean absolute difference: `2.5901627633556662e-18`.
- 73,084 values were not bit-identical due to runtime transcendental rounding.

This tests the local Reader function, not a complete app-level final export pipeline.

## Native/Python Base PCM parity

The C++ engine renders its quantized components through the same periodic-Hann OLA equation and writes integer Base PCM. The Python implementation remains a reference path. Both Base WAV files were byte-identical for synthetic PCM inputs at 8, 16, 24 and 32 bits. On the 48 kHz stereo test, all 1,920,000 Base PCM bytes matched.

## 10-second performance / fidelity workload

Synthetic RIFF/WAVE: 10 seconds, 48 kHz, stereo, signed 16-bit PCM; each channel contains three sinusoidal/chirped components. Environment: GCC 14.2.0, Node v22.16.0, Python 3.13.5, Linux execution container.

| Measurement | Result |
|---|---:|
| C++ FastGen elapsed | 0.80960091 s |
| Full FastGen → native Base → KRC capture wall time | 4.29595071 s |
| Audio duration / generator time | 12.20× |
| Frames | 2,001 |
| Components | 21,041 |
| KASF size | 158,294 bytes |
| Base WAV size | 1,920,044 bytes |
| KRM-IF size | 15,362,942 bytes |
| Source/Base SNR | 51.8664 dB |
| First 100 ms SNR | 48.9730 dB |
| Last 100 ms SNR | 49.5074 dB |

The benchmark result is archived in `benchmarks/RESULTS-Draft-0.5.md`. These are measurements from one synthetic case and one execution environment, not guarantees for real music, speech, other input formats, or the user's hardware.

## Exact KRC restoration

`verify_krmi` returned `PASS` with 960,000 channel samples checked. Source PCM SHA-256 and reconstructed PCM SHA-256 were both:

`aa27ab31cb5d3d6e9b5c93468ee0771c3ecb55e4aa79066573ca7108ddd49709`

The supplied Source WAV matched the embedded digest, and the restored WAV's PCM frame bytes were identical to the original. This proves exact reconstruction for the recorded Source/Base pair, not lossless KASF-only encoding.

## Scope limitations

- FastGen is a baseline, not the full Rev.0.9.20 Generator/KASE/MRA stack.
- Base rendering matches the local KASF05_Reader OLA path. The full application export, Source decode/resampling boundary and official float-to-integer PCM export are not yet established.
- `KRM-PROTO-PCM-Q-v1` applies no normalization and is explicitly an experimental KRM policy.
- KRM-IF physical container remains prototype v0.2 and is uncompressed.
- KASF v1 does not embed sample rate/sample count; retain the sidecar.

## Draft 0.6 temporal tracking additions

The suite now contains 45 tests. FastGen integration tests verify that:

1. the JSONL track map keeps a single track ID for a 440 Hz steady tone across every frame;
2. enabling default temporal tracking does not change KASF file bytes or Base WAV PCM bytes compared with `--no-tracking`;
3. Hungarian assignment is deterministic and does not alter KASF/Base payloads; and
4. the complete KASF → local Reader Base → KRC → KRM-IF path restores Source PCM exactly when Hungarian assignment is selected.

The synthetic metadata-only benchmark is in `benchmarks/measure_temporal_tracking.py`; measured output is stored in `benchmarks/temporal-tracking-measurements.json`. The real-audio solver comparison is documented in `benchmarks/TRACKER-ASSIGNMENT-COMPARISON-Draft-0.6.md`; `benchmarks/compare_tracker_assignment.py` reproduces the comparison for a supplied PCM WAV. Both `python -m krm_proto bridge-fast` and `python -m krm_proto.fastgen bridge` were exercised with `--tracker-assignment hungarian`. The track map is a hashed diagnostic sidecar, not part of the KASF v1 payload.


## Real-audio track association and KRM bridge test (Draft 0.6)

Two pre-existing Library WAV inputs were tested without modifying the originals. The following labels avoid embedding the source filenames in the report:

- Source A: mono, 48 kHz, 16-bit PCM, 415,744 samples/channel (8.661333 s).
- Source B: stereo, 44.1 kHz, 16-bit PCM, 749,025 samples/channel (16.984694 s).

FastGen parameters: 10 ms frames, up to 32 components/channel/frame, -58 dBFS threshold, 15 Hz minimum, symmetric half-hop edge guards.

| Metric | Source A | Source B |
|---|---:|---:|
| KASF frames | 1,734 | 3,391 |
| Components | 14,193 | 23,294 |
| Greedy-created tracks | 1,800 | 5,566 |
| Hungarian-created tracks | 1,541 | 5,286 |
| Source/Base SNR | 22.156 dB | 8.982 dB |
| KRM-IF size (Hungarian bridge) | 6,655,817 bytes | 23,973,513 bytes |
| KRM-IF verify | PASS | PASS |
| Restored PCM byte-identical to Source | Yes | Yes |

The Source/Base SNR values are intentionally not lossless scores: a low value means the baseline KASF representation leaves a larger Raw Residual. Exactness is a separate property. For both real inputs, KRM-IF verification passed and restored PCM was byte-identical to the supplied Source WAV PCM.

Hungarian mode modestly reduced track counts, but track lifetimes remain short on the stereo clip (median 2–3 frames). It is therefore an experimental association solver, not a solved real-audio tracker. Full per-channel lifetime distributions are in `benchmarks/TRACKER-ASSIGNMENT-COMPARISON-Draft-0.6.md`.


## Draft 0.8 — time-domain CDL verification

- Full automated suite: **66/66 passed** (`python -m unittest discover -s tests -v`).
- Python syntax/bytecode compilation: passed (`python -m compileall -q krm_proto krm_td_csc tests benchmarks`).
- Dictionary gradient: analytical time-domain gradient agrees with central finite differences.
- Unit-sphere atom constraint, deterministic learning, warm-start validation, variable-length training signals, and non-increasing accepted objective: passed.
- FISTA now checks both a small coefficient step and the proximal-gradient mapping before setting `converged=True`. In a 512-sample diagnostic, 80 and 200 iterations did not converge; a 500-iteration cap converged at iteration 441 with mapping norm `9.899120603835852e-6`.
- The outer CDL loop cannot report convergence when any coefficient solve in its final outer iteration is unfinished; a regression test forces one-iteration FISTA caps to verify this guard. Non-finite step/tolerance settings are rejected.
- The two small real-WAV experiments showed held-out validation improvements, but they are short-window exploratory benchmarks. Several coefficient subproblems hit their iteration caps and must not be described as fully converged. See `benchmarks/REPORT-DRAFT-0.8.md`.
- The time-domain CSC/CDL research modules were checked to contain no FFT/STFT/DCT calls.
