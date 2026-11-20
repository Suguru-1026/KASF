# Preserved KRM Stage11 — Silence-Based Primary Typing

This folder preserves the Stage11 source script, original summary, per-channel
region and percentage CSVs, plots, report, and the original SHA-256 manifest
from `KRM_Stage11_SilenceBasedTyping_2026-11-15.zip`.

The original ZIP did not save the full S0/S1/S2/S3 time-frequency cell map.
The integrated Stage11→Stage12 adapter therefore calls the preserved
`analysis/stage11_silence_typing.py::analyze_signal()` routine again on the
source residual array.

## Shared source input

The integrated Stage11 adapter reuses the canonical Stage08 input copy rather
than adding another NPZ under `krm_stage11/`. The older preserved Stage08
archive tree also retains its own original input copy:

`../research_archive/stage08_reader_v12_aligned_arrays.npz`

SHA-256: `c64c54999c8c1a0166e083affcf36a6466a6b4db9c52ba9305c0695a125d1faa`

The NPZ contains `R` with shape `(749025, 2)`. It is the diagnostic residual
pair described in `reports/STAGE11_REPORT.md`; `B` is a Reader v1.2 diagnostic
output carried through Stage10 and was not independently re-exported from the
browser UI.

## Algorithm

- Hann STFT, 44.1 kHz, NFFT 2048, hop 512, no boundary padding.
- Per-frequency temporal median power floor, median-smoothed over 9 frequency
  bins.
- S0 <6 dB; S1 6 to <12 dB; S2 12 to <24 dB; S3 >=24 dB above floor.
- Region candidates: 3×3 binary closing over S2/S3, 8-neighbour connected
  components, area >=4 cells and duration >=2 frames.

See `reports/STAGE11_REPORT.md` for interpretation limits and original run
results. See `../docs/STAGE11_STAGE12_INTEGRATION_REPORT.md` for replay parity
and Stage12 integration results.

## Integrated checksum

`SHA256SUMS.txt` verifies the preserved Stage11 files in this integrated
folder and the shared NPZ. `ORIGINAL_SHA256SUMS.txt` retains the source ZIP's
original checksum manifest unmodified; the original compiled `.pyc` entry is
not included in this source build.
