# KRM Complete v1.1.0 — Integrated Research Build

**KRM = Kino Residual / Component analysis system (project naming retained).**

This build consolidates the recoverable KRM Prototype Draft 0.8 source, the Draft 0.9 research bundle's integrated snapshot and TEA 0.2, the Stage08 research implementation/data, the original Stage11 silence-based typing source and outputs, a verified Stage11→Stage12 adapter, and the Stage12 v1 engine based on Stage12 Design Specification Draft 0.5.

> This is a consolidated research build, not a claim that every planned research method is production-ready or empirically validated. The build preserves uncertainty and missing interfaces instead of fabricating compatibility.

## Quick start

Python 3.10+. The KRM-IF and Stage12 core use the standard library. Stage11 replay requires NumPy and SciPy; the independent time-domain CSC/CDL research package requires NumPy.

```bash
python -m pip install -e .
# Stage11 replay adapter (NumPy + SciPy)
python -m pip install -e ".[stage11]"
# Optional: direct time-domain CSC/CDL research
python -m pip install -e ".[research]"

# CLI help
python -m krm_proto --help

# Verify / inspect / restore an existing KRM-IF file
python -m krm_proto verify --input sample.krmi --source source.wav
python -m krm_proto inspect --input sample.krmi
python -m krm_proto restore --input sample.krmi --output restored.wav

# Broad energy-activity probe (not a transient/source classifier)
python -m krm_proto analyze --input sample.krmi --output-json energy_events.json

# TEA time-domain candidate channel; streams WAV chunks, per channel
python -m krm_proto tea --input source.wav --output-json tea_candidates.json

# Re-run the preserved Stage11 detector and pass its cell map to Stage12 (per channel)
python -m krm_stage12.stage11_adapter research_archive/stage08_reader_v12_aligned_arrays.npz \
  --channel 0 --summary krm_stage11/outputs/stage11_summary.json \
  --output stage11_ch0_normalized.json --run-stage12 --stage12-output stage12_ch0

# Stage12 directly from an already normalized Stage11 cell map
python -m krm_proto stage12 --input normalized_stage11.json --output stage12_result

# Stage12 full rollback view (does not alter source input or original result)
python -m krm_proto stage12 --input normalized_stage11.json --output stage12_result --rollback-all

# Stage12 partial rollback of one active output region
python -m krm_proto stage12 --input normalized_stage11.json --output stage12_result --rollback-region MR-000001

# Native FastGen baseline (experimental; not the official full KASF stack)
python -m krm_proto generate-fast --input source.wav --output baseline.kasf
```

## Interactive test bench

Open `KRM_Workbench.html` in a modern browser. It runs offline and provides:

- Digital silence, persistent tone, impulse, intermittent tone, nearby tones, chirp, S1 and INVALID-gap test fixtures;
- adjustable B2/B3 gap and bridge-score controls;
- an editable input path via normalized Stage11 JSON upload (schema 1.0 and sparse complete-grid schema 1.1);
- a time-frequency cell-map view and event log;
- normalized input and preview report export.

The browser workbench is a **visual exploration preview**. Its bridge arbitration is deliberately simplified and is not the authoritative Stage12 engine. Use the Python `stage12` command for final results, rollback/replay, hashes and saved output bundles.

## Integrated architecture

```text
                    ┌───────────────────────────┐
Source PCM (X) ─────┤                           │
Base PCM (B) ───────┤ KRC / KRM-IF exact capture │──► immutable Raw Residual PCM (R = X - B)
                    └───────────────────────────┘                 │
                                                                  ▼
                  ┌────────────────────────────────────────────────────────┐
                  │                 Independent analysis channels          │
                  │                                                        │
                  │ Events ── broad RMS/activity candidates                │
                  │ TEA ───── time-domain transient/activity candidates     │
                  │ TD-CSC/CDL ─ selected-window waveform decomposition     │
                  │ Stage08 ─ hysteresis/gap research                       │
                  │ Stage11 ─ silence-based S0/S1/S2/S3 typing               │
                  │ Adapter ─ sparse complete grid → Stage12 1.1             │
                  │ Stage12 ─ region integration / structural labels          │
                  │ KRM-FC ─ advisory KASF candidate metadata validation    │
                  └────────────────────────────────────────────────────────┘
```

These channels are not fused into one opaque score. Their outputs have different semantics and are retained with method provenance. A detector proposal is not automatically an acoustic event, a source label, or a KASF component.

## Integration and compatibility gates

| Module | Integration status | Gate / restriction |
|---|---|---|
| KRC + KRM-IF | Core path | Exact integer residual, hashes/CRC and restore/verify remain authoritative |
| Events | Core analysis path | Broad activity only; never relabel as transient/source detection |
| TEA 0.2 | Integrated optional channel | Candidate output only; remains separate from Events and any missing MTA implementation |
| TD-CSC / CDL | Integrated research package | Selected windows only; NumPy required; non-convex research solver, not a default whole-file pass |
| Stage08 | Preserved research stage | Hysteresis/gap proposals are advisory; never hard-delete weak cells |
| Stage11 → Stage12 | Integrated and replay-verified | Original Stage11 `analyze_signal()` is called on the canonical residual NPZ; sparse S0-default grid is explicit in schema 1.1 |
| FastGen / local Reader | Experimental diagnostic path | Not equivalent to the official complete KASF Generator/Reader/export stack |
| Track Map | Metadata-only default | Does not change KASF bytes/Base PCM; experimental audio-changing refinement remains opt-in |
| KRM-FC candidate validation | Advisory | Schema/representability checks do not prove acoustic correctness or commit components |
| MTA / Spectral Novelty | Not included as runnable modules | Historical notes retained; archived executable source and complete frozen contracts were not recovered |
| EMD/HHT, VMD, Wavelet, SST, HPSS/STN, MP/Chirplet | Research roadmap / partial references only | Not exposed as automatically runnable production modules |

### Stage11 / Stage12 specific boundaries

- The recovered Stage11 bundle stores summary/region outputs and figures, but does not persist the full S0/S1/S2/S3 cell map. The adapter therefore replays the original Stage11 `analyze_signal()` from the canonical NPZ rather than inferring cells from region CSVs.
- The Stage11 input NPZ is byte-identical to the retained Stage08 NPZ. It is the source residual array, not a precomputed cell map.
- Stage12 normalized schema 1.1 supports a complete grid with sparse explicit records and an explicit implicit cell state. For this Stage11 route, omitted cells are S0; explicitly recorded INVALID cells remain INVALID. Legacy schema 1.0 still interprets omitted cells as INVALID.
- Stage11's saved summary class counts, grid dimensions, and candidate-region counts are checked against adapter replay before Stage12 is run.
- The included Stage08 results show why gap candidates must not be treated as hard exclusions: weak content can exist inside apparent gaps.
- Stage12 v1 uses the Draft 0.5 baseline, including 4-neighbour direct connectivity, conservative B2/B3/B4 bridging, immutable original regions, separate observed/bridge layers, RLE shapes, features and heuristic multi-label classification.
- Full rollback and active-region partial rollback are provided as non-destructive views. Partial rollback currently operates at the active merged-region boundary, not arbitrary intermediate event-branch surgery.
- Replay is a clean rerun from the immutable normalized input and config. Canonical output hashes exclude elapsed wall-clock time.
- The Ch0 real-data run measured about 497.4 MiB maximum RSS with default S1 bridging; this is close to the 512 MiB design target, not a hard or universal guarantee. No memory governor is enforced.

## Data integrity invariants

1. `R[n,c] = X[n,c] - B[n,c]` for the exact Source/Base integer PCM pair captured.
2. `X = B + R` restores the captured Source PCM exactly.
3. Analysis modules do not write to Raw Residual PCM.
4. Stage12 observed active cells are conserved; virtual connectors do not add observed cells or energy.
5. Original Stage12 regions are retained as immutable lineage roots.
6. Every analysis result must preserve input, algorithm, version and effective parameter provenance.

The local FastGen Reader bridge remains explicitly diagnostic. It must not be represented as the official KASF final Reader PCM without a separately verified export-equivalence test.

## Validation status

The build's current automated test suite is recorded in `BUILD_REPORT.md`. Passing synthetic/unit tests validate code behavior against those tests only. They do not establish real-audio detection quality, classifier accuracy, official KASF Reader parity, or the 512 MiB resource target.

## Main directories

- `krm_proto/` — KRC, KRM-IF, Reader bridge, FastGen, Events, TEA, predictor, recovery and CLI.
- `krm_td_csc/` — independent direct time-domain CSC/CDL research.
- `krm_stage11/` — preserved Stage11 source, original summary, regions, figures and report (the NPZ input is shared from `research_archive/`).
- `krm_stage12/` — Stage12 engine, native Stage11 replay adapter, feature extraction, classification, rollback/replay.
- `tests/` — consolidated regression suite.
- `benchmarks/` — research runners and prior measurements.
- `docs/` — design contracts, research reviews and Stage12 Draft 0.5.
- `research_archive/` — preserved Stage08 inputs/reports and original Draft 0.8 archive.
- `validation/stage11_stage12_realdata/` — per-channel real-data Stage12 outputs and validation logs.
- `KRM_Workbench.html` — offline interactive synthetic/normalized-map preview.

To rerun the archived Stage08 analysis, install the optional dependencies with `python -m pip install -e ".[stage08]"` and run `python research_archive/Stage08_Hysteresis_StableGapDetection/analysis/stage08_analysis.py` from a copied Stage08 working directory. The script writes outputs beside its bundled inputs; preserve the archived source bundle and use a copy for new runs.
