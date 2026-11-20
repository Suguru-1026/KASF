# KRM Stage12 v1.1.0 — Reference Build

Based on `KRM Stage12 Design Specification Draft 0.5`, integrated with the recovered Stage11 implementation dated 2026-11-15.

## Status

- Core build: implemented; normalized Stage11 schemas 1.0 and 1.1 supported.
- Stage11 source: preserved under `krm_stage11/`.
- Stage11 adapter: implemented; re-runs the preserved `analyze_signal()` routine from the canonical residual NPZ.
- Real-data integration: completed for Ch0 and Ch1; saved outputs are under `validation/stage11_stage12_realdata/`.
- Stage11 summary parity: input SHA, grid dimensions, S0-S3 class counts and candidate-region counts verified for both channels.
- Synthetic tests: included; see root `BUILD_REPORT.md`.
- Empirical classifier/bridge precision/recall/F1 gates: NOT YET VERIFIED.
- Memory: measured for the two integration runs; no hard memory governor or streaming implementation is claimed.

This is an integrated research build, not a claim that every Draft 0.5 empirical acceptance gate has passed.

## Requirements

Python 3.10+ for the full project. The Stage12 core itself uses the standard library. The Stage11 replay adapter requires NumPy and SciPy:

```bash
python -m pip install -e ".[stage11]"
```

## Run Stage11 → Stage12

Run each channel independently from the project root:

```bash
python -m krm_stage12.stage11_adapter \
  research_archive/stage08_reader_v12_aligned_arrays.npz \
  --channel 0 \
  --summary krm_stage11/outputs/stage11_summary.json \
  --output stage11_ch0_normalized.json \
  --run-stage12 --stage12-output stage12_ch0
```

Use `--channel 1` for the second channel. The adapter checks provenance and replay parity before exporting the map.

## Normalized input contracts

Top-level keys: `schema_version`, `input_manifest`, `cells`.

### Schema 1.0

`krm-stage11-normalized-1.0` uses a sparse `cells` object keyed by `"frame,bin"`. Each record uses `state` in `S0/S1/S2/S3/INVALID` and may carry `power`, `delta_db` and `local_floor_power`. Omitted cells mean INVALID.

### Schema 1.1

`krm-stage11-normalized-1.1` additionally requires `input_manifest.grid_complete=true` and `input_manifest.implicit_cell_state` set to `S0` or `INVALID`. Omitted cells are assigned exactly that declared state. Stage11 replay uses `implicit_cell_state="S0"` because the Stage11 algorithm classifies every cell in the complete grid. Explicit INVALID records are still INVALID. Other implicit activity states are rejected in v1.1 because they would require enumerating omitted active cells.

This avoids writing over a million explicit S0 JSON objects per channel without conflating silence-like cells with missing/invalid data.

## Important implementation notes

- Stage11 arrays are frequency-major `[bin, frame]`; the adapter maps them to Stage12 `(frame, bin)` coordinates and records the convention in the manifest.
- Stage11 region CSVs are not Stage12 inputs; Stage12 rebuilds regions from S2/S3 cells using its own Draft 0.5 procedures.
- Original Stage12 regions remain immutable roots; active observed cells are conserved; bridges are separate metadata.
- B1 uses 4-neighbour connectivity. B2/B3 bridge rules and B4 S1 eligibility follow the Stage12 Draft 0.5 implementation.
- Structural labels are heuristic fit scores, not probabilities or physical-cause diagnoses.
- Raw residual PCM is read-only and not modified by the adapter or Stage12.

## Real-data validation

See `docs/STAGE11_STAGE12_INTEGRATION_REPORT.md` for source provenance, parity checks, per-channel results, runtime/memory measurements, and limitations.
