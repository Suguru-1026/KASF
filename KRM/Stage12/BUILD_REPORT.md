# KRM Complete v1.1.0 — Build & Validation Report

Date: 2026-11-17

## Build scope

Integrated source: KRM Prototype Draft 0.8 + Draft 0.9 research-bundle integrated snapshot / TEA 0.2 + Stage08 archive and input data + recovered Stage11 source and outputs + Stage11→Stage12 replay adapter + Stage12 Draft 0.5 reference engine.

The Stage11 adapter uses the byte-verified canonical Stage08 input at `research_archive/stage08_reader_v12_aligned_arrays.npz` rather than adding another copy inside `krm_stage11/`. The preserved Stage08 archive tree also retains its historic bundled input copy.

## Automated tests

- Consolidated `unittest` suite: **116 / 116 PASS**.
  - Existing integrated Draft 0.8 + TEA regression suite: 78 tests.
  - Stage12 original reference tests: 11 tests.
  - Stage12 integration tests (hash/replay/rollback/input validation): 5 tests.
  - Stage12 acceptance-oriented synthetic cases: 16 tests.
  - Stage11 adapter and implicit-grid semantics: 6 tests.
- `compileall` over `krm_proto`, `krm_td_csc`, `krm_stage11`, `krm_stage12`, `tests`, and `benchmarks`: PASS.
- CLI smoke tests: `python -m krm_proto --help`, `python -m krm_stage12.cli --help`, and `python -m krm_stage12.stage11_adapter --help`: PASS.
- Stage11 adapter synthetic replay: PASS; frequency-major `[bin,frame]` → Stage12 `[frame,bin]` coordinate mapping verified.
- Recovered Stage11 real-data replay: PASS for Ch0 and Ch1; NPZ SHA, grid dimensions, S0/S1/S2/S3 counts, candidate-region counts and full candidate-region records agree with the saved Stage11 summary.
- Stage12 real-data runs: PASS for both channels with default S1 bridging; observed-cell conservation and RLE round-trip passed.
- TEA WAV CLI smoke test on a generated mono PCM WAV: PASS; 2 impulse candidates detected.
- Browser workbench JavaScript syntax check and headless smoke test: PASS; normalized schema 1.0 and 1.1 are accepted, and implicit S0 is shown as S0 rather than INVALID.

## Stage12 synthetic smoke benchmark

One deterministic run with seed `20261117`:

| Metric | Result |
|---|---:|
| Grid | 80 frames × 192 bins = 15,360 cells |
| Active cells | 1,850 |
| Original regions | 1,620 |
| Active output regions | 558 |
| Wall time | 2.566 s |
| Python tracemalloc peak | 15.41 MiB |
| Active cell conservation | PASS |

This is a single sparse synthetic smoke benchmark, not a broad scaling study. `tracemalloc` is not process RSS and does not prove a memory cap. Full result and canonical hash are in `validation/stage12_synthetic_benchmark_80x192.json`.

## Stage11 → Stage12 recovered real-data integration

The original Stage11 source `analyze_signal()` is preserved under `krm_stage11/analysis/` and called directly by `krm_stage12.stage11_adapter`. The Stage11 archive did not persist the complete per-cell map, so the adapter replays the original algorithm from `R`; it does not infer per-cell labels from the saved region CSVs.

| Metric | Ch0 | Ch1 |
|---|---:|---:|
| Grid | 1,459 frames × 1,025 bins | 1,459 frames × 1,025 bins |
| Total cells | 1,495,475 | 1,495,475 |
| S0 | 1,185,213 | 1,270,888 |
| S1 | 209,553 | 151,892 |
| S2 | 98,791 | 65,277 |
| S3 | 1,918 | 7,418 |
| Stage11 retained candidate regions | 1,329 | 615 |
| S2/S3 cells passed to Stage12 | 100,709 | 72,695 |
| Stage12-A original regions | 36,647 | 20,045 |
| Stage12 final active regions | 7,180 | 3,381 |
| Accepted S1 bridges | 2,777 | 1,084 |
| Accepted B2 temporal edges | 13 | 11 |
| Accepted B3 frequency edges | 68 | 22 |
| Cell conservation / RLE | PASS / PASS | PASS / PASS |

Stage11 and Stage12 region counts differ by design: Stage11 uses 3×3 binary closing and 8-neighbour connected components; Stage12-A extracts frame-local S2/S3 runs and applies its own 4-neighbour and constrained bridge stages.

Runtime and resident-memory measurements (Linux `/usr/bin/time -v`):

| Run | Wall time | Maximum RSS |
|---|---:|---:|
| Ch0, default config with S1 bridge | 14.85 s | 509,316 KiB (about 497.4 MiB) |
| Ch0, comparison with S1 bridge disabled | 9.44 s | 433,560 KiB (about 423.4 MiB) |
| Ch1, default config with S1 bridge | 7.36 s | 332,528 KiB (about 324.7 MiB) |

These are measurements for this exact dataset and environment only. Ch0 is close to the 512 MiB design target. No hard memory governor, streaming, or checkpointed chunk-boundary execution is implemented.

Detailed provenance, adapter semantics, results and reproduction commands are in `docs/STAGE11_STAGE12_INTEGRATION_REPORT.md`. Final Stage12 bundles are in `validation/stage11_stage12_realdata/`.

## Stage08 reproducibility check

The archived Stage08 analysis script was run against a temporary copy of the included `reader_v12_aligned_arrays.npz`. The generated `stage08_summary.json` was byte-identical to the archived summary. This verifies reproducibility of that Stage08 run in the current environment; it does not convert Stage08 output into Stage11 cells or prove the Stage08 gap proposals are safe exclusions.

Stage08's documented weak-in-gap synthetic tests show the priority gap tier can falsely exclude weak bands; the guarded tier avoids those false exclusions but also has no recall for the intended clean gap in those tests. Therefore, gap output remains advisory.

## Corrections and integration improvements

1. Stage12 B2→B3 now propagates aggregate bounding-box fields.
2. Stage12 B4 uses linear power and local floor for `10*log10(P/floor)`, not `delta_db` as if it were linear power.
3. B2 support dilation is a true one-bin set dilation and preserves internal holes.
4. Bridge candidate generation uses bounded-gap temporal/frequency buckets rather than scanning all region pairs.
5. Bounding-box union checks no longer expand large rectangles into individual cells.
6. Undefined temporal continuity is not silently imputed for Tonal scoring.
7. Input validation checks finite values, boolean-vs-integer mistakes, canonical cell keys, and fixed Draft 0.5 caps.
8. Stable IDs and canonical result hashes exclude elapsed wall-clock time.
9. Connected-component discovery now uses deterministic sorted seeds and emits components incrementally; original-region lookup is indexed instead of repeatedly scanning the full list.
10. Stage12 reads sparse cell fields through views rather than copying the Stage11 state, power, activity and floor data into multiple additional coordinate maps.
11. Normalized Stage11 schema 1.1 explicitly separates complete-grid implicit S0 from INVALID. Schema 1.0 retains its former missing-cell-as-INVALID behavior.

## Not certified / remaining boundaries

- The original Stage11 bundle did not store a complete cell-map serialization. The adapter re-executes Stage11 from the verified residual NPZ; it is not an importer for a persisted native cell-map file.
- Stage11 provenance states that `B` is a Reader v1.2 diagnostic output carried through Stage10, not independently re-exported from the browser UI. Findings apply to that diagnostic pair.
- Stage12 classification scores are heuristic structural fit scores, not probabilities or physical-cause diagnoses.
- The 16 synthetic Stage12 cases and two real-data runs do not establish broad bridge precision/recall/F1 or classification macro-F1.
- Stage12 partial rollback is implemented at active merged-region granularity; arbitrary intermediate event-branch rollback is not exposed.
- No hard 512 MiB memory governor, streaming, or checkpointed chunk-boundary continuation is implemented.
- No official KASF full Generator/Reader/export parity is claimed for FastGen's local diagnostic Reader bridge.
- MTA and Spectral Novelty executable modules were not present in the archived research bundle; historical notes are retained but implementations are not fabricated.
- EMD/HHT, VMD, Wavelet, SST, HPSS/STN and MP/Chirplet are not all wired as runnable modules.
- The offline HTML Workbench remains a preview implementation with simplified bridge arbitration. Python Stage12 is authoritative.

## Release statement

KRM Complete v1.1.0 is an integrated research build with preserved Stage11 source, a parity-checked Stage11 replay adapter, real-data Stage12 runs on both channels, exact residual preservation, KRM-IF/CLI capabilities, optional TEA and TD-CSC/CDL research paths, and an offline interactive workbench. It does not claim that every roadmap algorithm, quality metric, production memory guarantee, or official KASF Reader parity target is complete.
