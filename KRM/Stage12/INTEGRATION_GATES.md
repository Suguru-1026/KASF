# KRM Integration Gates — v1.1.0

## Purpose

KRM intentionally uses multiple independent analysis channels. Integration means sharing provenance and compatible data contracts, not forcing all algorithms into a single decision score.

## Gate A — data integrity

A module may receive Raw Residual PCM only through a read-only view. It must not rewrite the KRM-IF payload, source data, Base PCM, or residual blocks. Any derived representation must identify its parent input hash and algorithm/config version.

## Gate B — time-domain candidate channels

- Events is a broad energy-activity probe.
- TEA is a time-domain transient/activity candidate detector.
- These are independent proposal channels. Do not use naive OR fusion as an automatic acceptance decision.
- A proposal may be associated with another proposal by overlap/nearby interval, but both source methods and their original measurements remain visible.
- MTA is not enabled because its archived executable source and frozen complete contract were not recovered. The historical research notes are not sufficient to recreate it faithfully.

## Gate C — selected-region decomposition

TD-CSC/CDL is a direct waveform-domain research track. It is eligible only when:

1. the target interval has explicit sample bounds and source provenance;
2. the selected window fits the configured memory/time budget;
3. dictionary/solver settings and convergence status are recorded;
4. the solver does not overwrite the source or residual;
5. the result is treated as a model-based decomposition, not a guaranteed physical source separation.

It is not automatically run across an entire recording by default.

## Gate D — Stage08 / Stage12

- Stage08 produces hysteresis and gap candidates, not a safe deletion mask.
- The integrated adapter calls the preserved Stage11 `analyze_signal()` implementation on the exact residual NPZ; it does not reconstruct cells from region CSVs.
- Stage11's saved summary is checked for input hash, grid dimensions, class counts and candidate-region count before the normalized map is accepted.
- Sparse schema 1.1 declares `grid_complete=true` and `implicit_cell_state="S0"`; omitted cells therefore mean known S0 only for this complete-grid input. Explicit INVALID cells remain invalid.
- Legacy schema 1.0 retains its original rule: omitted cells mean INVALID.
- S0/S1/S2/S3 thresholds and floor method are recorded from the preserved Stage11 implementation and actual manifest; the workbench does not infer them.
- B2/B3 bridges may pass across valid S0 gaps subject to support/level constraints. INVALID and S1 are not treated as S0. B4 is a constrained observed S1 path. Connectors remain separate from observed cells.

## Gate E — KRM-FC

A candidate proposal can pass schema and KASF representability checks yet still be acoustically wrong. It remains advisory until a separate acceptance/commit policy exists. No automatic write-back to KASF is enabled.

## Gate F — experimental KASF bridge

FastGen and its local Reader output are an independent baseline. They may be used for diagnostic research when clearly labeled, but must not be substituted for official KASF final Reader/export output in claims about residual quality.

## Current integration decisions

| Pair / route | Decision | Reason |
|---|---|---|
| Events + TEA | Parallel channels | Different detector semantics; preserve one-sided proposals |
| TEA + TD-CSC/CDL | Candidate → selected-window analysis only | CSC/CDL is computationally heavier and not an onset detector |
| Stage08/Stage07 residual NPZ → Stage11 → Stage12 | Allowed through preserved adapter | Replays exact Stage11 source, validates saved summary parity, explicit sparse complete-grid contract |
| Stage11 region CSV → Stage12 | Not allowed | Region candidates are not a complete per-cell S0/S1/S2/S3 map |
| Normalized Stage11 schema 1.0 → Stage12 | Allowed | Omitted cells remain INVALID |
| Normalized Stage11 schema 1.1 → Stage12 | Allowed | Requires complete-grid declaration and explicit implicit-cell state |
| Stage12 → KRM-FC | Not automatic | Region structure does not prove KASF representability |
| FastGen local Base → canonical residual claims | Not allowed | Local Reader/export parity not established |
