# KRM Stage 08 — Hysteresis & Stable Spectral Gap Detection

## Goal
Reduce boundary flicker and avoid excluding weak-but-real residual content when deriving frequency search intervals.

## Detector
- Local spectra inherited from Stage 07: Hann STFT, NFFT 2048, hop 512; 0.5 s pooling, 0.1 s step, 9-bin smoothing.
- Six enter/hold pairs: -15/-20, -18/-23, -20/-25, -25/-30, -28/-33, -35/-40 dB relative to each local spectral peak.
- Per frequency bin, enter active at the first threshold; remain active while above the more permissive hold threshold.
- Fill one-local-window time dropouts using a 3-window closing operation.
- Candidate gaps are inactive bins between outermost active runs; minimum 200 Hz width and 0.3 s duration.
- Priority gaps require agreement from the first three threshold pairs; these are only search-priority hints.
- Guarded gaps require agreement from all six pairs through -35/-40 dB; these are more conservative but still not hard exclusions.
- The union of active masks is retained for search preservation.

## Real recording findings
The recording remains strongly channel-dependent. See `outputs/real_consensus_gap_regions.csv` and `outputs/transition_stability.csv`.
Consensus gaps are threshold-dependent candidate regions only. Absence of a consensus gap does not imply that no gap exists; it can also indicate low confidence or broad residual occupancy.

## Synthetic false-exclusion tests
Six controlled cases were tested: clean separated bands, three weak-signal levels inside the nominal gap, a temporary signal intruding into the gap, and broadband noise. Known occupied regions were compared against the conservative consensus gap mask.
False exclusion is measured as known occupied signal time-frequency cells marked as gap. The priority tier can flag weak occupied content: in the weak-band tests it excludes 92% of the weak band. The guarded tier preserves those tested weak bands, but also has zero gap recall in these six cases. Neither tier authorizes irreversible pruning.

- **clean_two_band**: priority false exclusion=0.000%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=51.22%/0.00%; priority/guarded weak-band exclusion=n/a/n/a; candidate regions priority/guarded=1/0.
- **weak_in_gap_20db**: priority false exclusion=10.481%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=52.00%/0.00%; priority/guarded weak-band exclusion=92.00%/0.00%; candidate regions priority/guarded=1/0.
- **weak_in_gap_26db**: priority false exclusion=10.481%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=52.00%/0.00%; priority/guarded weak-band exclusion=92.00%/0.00%; candidate regions priority/guarded=1/0.
- **weak_in_gap_36db**: priority false exclusion=10.481%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=50.87%/0.00%; priority/guarded weak-band exclusion=92.00%/0.00%; candidate regions priority/guarded=1/0.
- **temporary_in_gap**: priority false exclusion=0.000%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=38.04%/0.00%; priority/guarded weak-band exclusion=0.00%/0.00%; candidate regions priority/guarded=2/0.
- **broadband**: priority false exclusion=0.000%; guarded false exclusion=0.000%; priority/guarded 1–2 kHz gap recall=n/a/n/a; priority/guarded weak-band exclusion=n/a/n/a; candidate regions priority/guarded=0/0.

## Stage 07 comparison
`outputs/stage07_vs_stage08_false_exclusion.csv` compares Stage 07 one-threshold behavior, Stage 08 priority candidates (3 pairs), and Stage 08 guarded candidates (6 pairs). The guarded tier reduces false exclusion in these tests but returns no usable gap in this recording and has zero expected-gap recall in the synthetic tests.

## Interpretation and recommended KRM use
- Use priority gaps only to rank or downweight intervals.
- Use guarded gaps as stronger low-energy candidates, still not permanent exclusions.
- Preserve the union of active masks and all weak/uncertain bins for fallback search.
- Store the enter/hold thresholds and confidence with every gap.
- Re-check candidates at multiple NFFT/local-window sizes before structural classification.

## Limits
This evaluation is based on one real residual recording plus six controlled synthetic cases. No general accuracy claim is justified. A gap is always a threshold-defined low-energy interval, not proof of absolute silence.
