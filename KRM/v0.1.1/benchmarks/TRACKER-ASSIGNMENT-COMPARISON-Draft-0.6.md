# Temporal Assignment Comparison — Draft 0.6

Date: 2026-11-14

## Scope

Greedy and Hungarian assignment were compared using two PCM WAV files already present in the user's Library. The original files were read-only inputs; all outputs were written to a separate test directory. No audio samples are included in this package.

FastGen settings: 10 ms frames, 32 maximum components per channel/frame, -58 dBFS threshold, 15 Hz minimum frequency, symmetric half-hop edge guards. Measurements below are native C++ generator elapsed times without Base WAV rendering, unless stated otherwise.

## Input profiles and results

| Measure | Source A | Source B |
|---|---:|---:|
| Sample rate | 48,000 Hz | 44,100 Hz |
| Channels | 1 | 2 |
| Duration | 8.661333 s | 16.984694 s |
| KASF frames | 1,734 | 3,391 |
| Total components | 14,193 | 23,294 |

### Overall solver comparison

| Input / method | Generator time | Tracks created | Matches |
|---|---:|---:|---:|
| A / Greedy | 0.286 s | 1,800 | 12,393 |
| A / Hungarian | 0.367 s | 1,541 | 12,652 |
| B / Greedy | 0.511 s | 5,566 | 17,728 |
| B / Hungarian | 0.679 s | 5,286 | 18,008 |

Hungarian reduced created track IDs by 14.4% on Source A and 5.0% on Source B, while adding runtime. This is a useful local assignment improvement, not proof of reliable musical-object tracking.

### Track lifetime distribution

A track's lifetime here is the number of frames containing its ID. It does not count the frames where it was absent.

| Input / channel / method | Tracks | Median frames | 90th percentile | Longest | Tracks ≥10 frames | Tracks ≥50 frames |
|---|---:|---:|---:|---:|---:|---:|
| A / mono / Greedy | 1,800 | 5 | 18 | 53 | 511 | 3 |
| A / mono / Hungarian | 1,541 | 6 | 22 | 79 | 512 | 13 |
| B / ch 0 / Greedy | 3,808 | 3 | 9 | 49 | 368 | 0 |
| B / ch 0 / Hungarian | 3,604 | 3 | 10 | 60 | 396 | 1 |
| B / ch 1 / Greedy | 1,758 | 2 | 11 | 53 | 212 | 1 |
| B / ch 1 / Hungarian | 1,682 | 2 | 12 | 71 | 229 | 1 |

The stereo recording remains highly fragmented: median track lifetimes are only 2–3 frames. Hungarian improves the tail modestly but does not solve the main problem.

## Payload invariants

For each source, the complete KASF file and native Base WAV were compared between assignment modes:

- Source A: KASF bytes identical; Base WAV bytes identical.
- Source B: KASF bytes identical; Base WAV bytes identical.

This is expected because assignment mode changes track metadata only. The Base PCM is not modified by track matching.

## End-to-end KRM bridge verification with Hungarian

Both sources were also processed through FastGen → native local Reader Base → KRC → KRM-IF → restore.

| Measure | Source A | Source B |
|---|---:|---:|
| KRM-IF size | 6,655,817 bytes | 23,973,513 bytes |
| KRM-IF verify | PASS | PASS |
| Restored PCM bytes equal Source PCM | Yes | Yes |
| Source/Base SNR | 22.156 dB | 8.982 dB |

The low Source/Base SNR means the baseline KASF representation leaves a large residual, particularly in Source B. It does **not** mean KRM lost audio: the integer residual `R = X - B` restored the exact original PCM in both cases. The exactness claim applies to the captured Source/Base pair and this prototype bridge, not to KASF-only coding or the full official KASF application export.

## Decision

Keep Greedy as the default because Hungarian adds processing cost while the improvement in track lifetime remains modest. Keep Hungarian available for offline diagnostics and future association research. The next substantial tracking improvement should likely address the framewise component set itself—persistence, attack/decay handling, harmonic grouping, and cross-frame candidate confidence—rather than only changing the assignment solver.
