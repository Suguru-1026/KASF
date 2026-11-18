# KRM Stage 08 — Hysteresis & Stable Spectral Gap Detection

Stage 08 adds per-frequency temporal hysteresis, one-window dropout bridging, and two tiers of gap candidates: a 3-pair priority mask and a 6-pair guarded mask. It evaluates false exclusion on clean two-band, three weak in-gap signal levels, temporary in-gap content, and broadband noise.

## Inputs
- `inputs/reader_v12_aligned_arrays.npz`: Stage 07 Reader v1.2 aligned Source/Base/Residual arrays and KASF frame metadata.

## Main outputs
- `outputs/real_consensus_gap_regions.csv`: real-recording priority and guarded candidate gaps, labelled by tier.
- `outputs/real_local_outer_bounds.csv`: bounds by hysteresis pair and local time.
- `outputs/transition_stability.csv`: raw-threshold vs hysteresis transition counts.
- `outputs/synthetic_false_exclusion_evaluation.csv`: known-signal false-exclusion evaluation for both tiers.
- `outputs/stage07_vs_stage08_false_exclusion.csv`: comparison to one-threshold detector.
- `outputs/stage08_summary.json`: complete machine-readable summary.
- `figures/`: real and synthetic confidence maps.

## Reproduction
Requires Python 3.10+, NumPy, SciPy, and Matplotlib. Run `python analysis/stage08_analysis.py`.
