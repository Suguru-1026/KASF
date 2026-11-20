# KRM Stage 11 — Silence-Based Primary Typing

## Goal
Introduce a conservative first-pass activity typing before semantic residual classification. Raw Residual PCM is never modified.

## Types
- S0: silence-like; below 6 dB above the estimated local frequency floor. This is not proof of exact digital silence or inaudibility.
- S1: low/ambiguous activity; 6 to <12 dB above floor. Kept separate to avoid discarding weak residuals.
- S2: active; 12 to <24 dB above floor.
- S3: high activity; >=24 dB above floor. High activity is not automatically important or erroneous.

## Detector
Hann STFT, NFFT 2048, hop 512, 44.1 kHz. Per-frequency floor is the temporal median of power, median-smoothed over 9 frequency bins. S2/S3 cells are grouped using 3x3 binary closing and 8-neighbour connected components. Components are retained at >=4 cells and >=2 frames.

## Synthetic smoke tests
Digital silence produced 100% S0 and zero candidate regions. Stationary white noise produced 93.63% S0 and 6.37% S1, with zero S2/S3 cells and zero retained regions. A persistent tone, intermittent tone bursts, a chirp, and a short broadband burst produced retained regions. In the intermittent-tone test, 62.86% of target-band cells during the three known burst windows were S2/S3. This is a functional check only, not a general precision/recall benchmark.

## Diagnostic residual results
- Ch0: S0 79.25%, S1 14.01%, S2 6.61%, S3 0.13%; 1,329 retained candidate regions.
- Ch1: S0 84.98%, S1 10.16%, S2 4.36%, S3 0.50%; 615 retained candidate regions.

## Interpretation limits
The labels are relative to an estimated floor and depend on the recording. S0 is silence-like, not absolute silence. A persistent component can raise the floor estimate; tonal leakage can spread activity across bins. Region candidates are not semantic classifications and must not be used to delete residual data. Synthetic cases are controlled functional tests, not a general benchmark.

## Data provenance
Input arrays are carried from Stage 10. The Base signal is a Reader v1.2 diagnostic output, not independently re-exported from the browser UI. Findings are specific to this diagnostic pair.

## Next step
Review false-positive region counts under stationary noise and missed weak activity. Tune thresholds only against a broader synthetic suite and independently verified KASF Reader output.
