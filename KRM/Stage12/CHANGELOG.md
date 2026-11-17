# Changelog — KRM Complete

## v1.1.0 — 2026-11-17

- Recovered and preserved the original Stage11 silence-based typing source, output summaries, per-channel region CSVs, figures, report and checksum manifest.
- Added a deterministic Stage11 replay adapter to Stage12 using the canonical shared residual NPZ; verified both channels against the archived Stage11 summary.
- Added normalized Stage11 schema 1.1 with complete-grid / implicit-state semantics; S0 omission is distinct from INVALID.
- Updated Stage12 to use sparse cell-field views, stream deterministic component generation, and avoid repeated O(N²)-like lookup patterns on sparse real data.
- Ran Stage12 on both real channels with default S1 bridging; observed-cell conservation and RLE round-trip passed.
- Added real-data output bundles, integration report and adapter test coverage.

## v1.0.0 — 2026-11-17

- Consolidated the Draft 0.8 integrated source tree and TEA 0.2 research overlay.
- Added the Stage12 package based on Design Specification Draft 0.5.
- Added Stage12 CLI, canonical result hashing, deterministic replay entry point, full rollback and active-region partial rollback views.
- Hardened Stage12 config and normalized input numeric validation.
- Corrected Stage12 B2→B3 chained-merge bounding-box propagation.
- Replaced the Stage12 bridge pass all-pairs scan with bounded-gap buckets.
- Corrected B2 support dilation to preserve internal support holes.
- Corrected classifier behavior so undefined temporal continuity is not silently imputed for Tonal scoring.
- Added TEA WAV CLI with bounded chunk processing per channel.
- Added an offline interactive browser workbench for synthetic/normalized-map preview.
- Preserved Stage08 code, input arrays, reports and original Draft 0.8 archive for provenance.
- Added explicit integration gates and limitations; did not fabricate missing MTA, Spectral Novelty or native Stage11 adapters.
