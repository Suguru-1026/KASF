# Stage11 → Stage12 Real-Data Integration Report

Date: 2026-11-17  
Integration build: KRM Complete v1.1.0  
Source bundle: `KRM_Stage11_SilenceBasedTyping_2026-11-15.zip`

## 1. Recovered Stage11 source

The recovered Stage11 implementation is preserved under `krm_stage11/`.
The adapter imports and calls the original `analyze_signal()` function; it does
not replace the Stage11 detector with a new approximation.

The Stage11 source settings are:

- Hann STFT, 44,100 Hz, NFFT 2,048, hop 512;
- per-frequency temporal median power floor;
- 9-bin median smoothing over frequency;
- S0 below 6 dB, S1 6 to <12 dB, S2 12 to <24 dB, S3 at least 24 dB above floor;
- Stage11 region candidates are 3×3 binary closing on S2/S3, 8-neighbour labels,
  area at least 4 cells and duration at least 2 frames.

The original Stage11 summary, per-channel region CSVs, typing-percentage CSVs,
figures, report, source code, and original checksum manifest are preserved.
The Stage11 input NPZ is byte-identical to the single canonical copy already
stored as `research_archive/stage08_reader_v12_aligned_arrays.npz`; the input
is not duplicated.

## 2. Adapter behavior

`krm_stage12.stage11_adapter` reloads the `R` arrays from the original NPZ and
re-executes the Stage11 source routine. The Stage11 arrays use
`[frequency_bin, frame]`; the adapter explicitly maps them to Stage12's
`[frame, frequency_bin]` cell keys.

The Stage11 output does not persist a complete serialized cell map. Therefore,
the adapter regenerates it from the source residual arrays rather than
pretending that the Stage11 summary/region CSVs are a full cell map.

The normalized schema is `krm-stage11-normalized-1.1`:

- `grid_complete=true` declares that the full rectangular grid was classified;
- `implicit_cell_state="S0"` means omitted sparse entries are known S0 cells;
- S1/S2/S3 records are explicitly stored with required power/floor/activity data;
- an explicitly recorded `INVALID` remains invalid and is never conflated with
  the implicit S0 state.

Legacy `krm-stage11-normalized-1.0` remains supported. In 1.0, omitted cells
continue to mean INVALID. The two omission semantics are not interchanged.

The adapter validates the NPZ SHA-256 against the archived Stage11 summary,
checks the grid dimensions and all S0/S1/S2/S3 class counts, and compares both
the candidate-region count and the complete ordered candidate-region records
against the saved Stage11 summary. It records source, algorithm and summary
hashes in the input manifest.

## 3. Stage11 parity against saved results

Both channels reproduced the saved Stage11 summary exactly for grid size and
S0/S1/S2/S3 cell counts, and the candidate-region counts agreed.

| Metric | Ch0 | Ch1 |
|---|---:|---:|
| Frames | 1,459 | 1,459 |
| Frequency bins | 1,025 | 1,025 |
| Total cells | 1,495,475 | 1,495,475 |
| S0 | 1,185,213 | 1,270,888 |
| S1 | 209,553 | 151,892 |
| S2 | 98,791 | 65,277 |
| S3 | 1,918 | 7,418 |
| Stage11 candidate regions | 1,329 | 615 |
| Sparse S1/S2/S3 records | 310,262 | 224,587 |

## 4. Stage12 results using default Draft 0.5 configuration

Both real-data runs completed with the default configuration, including S1
bridging. Stage12 conserves all S2/S3 observed cells; bridges are recorded as
separate metadata and do not add observed cells.

| Metric | Ch0 | Ch1 |
|---|---:|---:|
| S2/S3 input cells | 100,709 | 72,695 |
| Stage12-A original regions | 36,647 | 20,045 |
| Final active regions | 7,180 | 3,381 |
| Accepted S1 bridges | 2,777 | 1,084 |
| Accepted B2 temporal edges | 13 | 11 |
| Accepted B3 frequency edges | 68 | 22 |
| Cell conservation | PASS | PASS |
| RLE roundtrip | PASS | PASS |
| Raw PCM mutated | No | No |

Canonical Stage12 run hashes:

- Ch0: `4f9a06e87ed26eaade33c257f690e3748f65b2134bdb56d76df87d9f794a8d78`
- Ch1: `201c088ee8071bbdca1676509aabf599d400ecb0fc7e477343bbe5d00a2c0e44`

These region counts are not expected to match Stage11's candidate-region counts.
Stage11 region candidates use 3×3 closing and 8-neighbour connected
components; Stage12-A independently extracts frame-local S2/S3 runs and
Stage12-B applies its 4-neighbour and constrained bridge rules.

Stage12 output bundles are stored in
`validation/stage11_stage12_realdata/ch0_default/` and
`validation/stage11_stage12_realdata/ch1_default/`.

## 5. Runtime and memory smoke measurements

Measured in this Linux build environment with `/usr/bin/time -v`:

| Run | Wall time | Maximum RSS |
|---|---:|---:|
| Ch0, S1 bridge enabled | 14.85 s | 509,316 KiB (about 497.4 MiB) |
| Ch0, S1 bridge disabled (comparison) | 9.44 s | 433,560 KiB (about 423.4 MiB) |
| Ch1, S1 bridge enabled | 7.36 s | 332,528 KiB (about 324.7 MiB) |

These are specific smoke measurements, not a hard memory governor or a
universal guarantee. Ch0 with S1 bridging is close to the 512 MiB target.
The Python Stage12 core still uses in-memory structures; no streaming or
checkpointed chunk boundary execution is claimed.

During real-data integration, two scalability defects were corrected:

1. Component discovery no longer recomputes `min(unseen)` for every connected
   component; it now uses deterministic sorted seeds and yields components
   incrementally.
2. Original-region lookup is indexed by ID instead of repeatedly scanning the
   full original-region list. Sparse cell fields are read through views rather
   than copied into several duplicate coordinate maps.

## 6. Interpretation and limitations

- Stage11's `S0` is silence-like relative to the estimated floor, not exact
  digital silence or proof of inaudibility.
- Stage11's input provenance identifies `B` as a Reader v1.2 diagnostic output
  carried through Stage10, not an independently re-exported browser Reader PCM.
  Results apply to this diagnostic pair.
- Stage12 Transient / Tonal / Diffuse outputs are heuristic structural fit
  labels, not probabilities or physical-cause diagnoses.
- The 16 Stage12 synthetic acceptance cases and these two real-data runs do not
  establish general classifier precision/recall/F1 or bridge quality across a
  broad corpus.
- The original Stage11 region CSVs are retained but are not used as direct
  Stage12 input. Stage12 requires the per-cell state map generated by the
  adapter.

## 7. Reproduction commands

From the KRM Complete project root, install the Stage11 dependencies:

```bash
python -m pip install -e ".[stage11]"
```

Then execute each channel independently:

```bash
python -m krm_stage12.stage11_adapter \
  research_archive/stage08_reader_v12_aligned_arrays.npz \
  --channel 0 \
  --summary krm_stage11/outputs/stage11_summary.json \
  --output stage11_ch0_normalized.json \
  --run-stage12 --stage12-output stage12_ch0

python -m krm_stage12.stage11_adapter \
  research_archive/stage08_reader_v12_aligned_arrays.npz \
  --channel 1 \
  --summary krm_stage11/outputs/stage11_summary.json \
  --output stage11_ch1_normalized.json \
  --run-stage12 --stage12-output stage12_ch1
```

The normalized JSON files are generated on demand and are not duplicated in the
release archive. Each is roughly 20–30 MB for this dataset.
