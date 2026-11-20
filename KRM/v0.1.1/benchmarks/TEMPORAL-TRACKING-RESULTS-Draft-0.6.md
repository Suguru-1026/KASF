# Temporal Track Map Validation — Draft 0.6

Date: 2026-11-14

## Test setup

- Synthetic WAV: 2.0 seconds, 16 kHz, stereo, signed 16-bit PCM.
- Each channel contains a slowly modulated main tone plus a second steady partial.
- FastGen: 50 ms frames, maximum 4 components per channel/frame, threshold -58 dBFS, minimum frequency 20 Hz, half-hop edge guards.
- Three wall-time repeats per mode; median reported only as a rough execution-container observation.

## Results

| Measure | Tracking disabled | Tracking enabled |
|---|---:|---:|
| Median Python wrapper wall time | 33.3 ms | 31.7 ms |
| Base SNR | 50.318 dB | 50.318 dB |
| Base PCM bytes | 128,000 | 128,000 |

The timing difference is within expected short-run process / filesystem variation and must not be interpreted as a speedup. The important invariant is that default tracking is metadata-only.

- KASF output files: byte-identical.
- Base PCM files: byte-identical.
- Track map rows: 162, matching 81 frames × 2 channels.
- Unique track IDs: 8 in channel 0 and 6 in channel 1. This includes weaker residual components and fragmented tracks.
- Persistent dominant tracks: 2 per channel, using a diagnostic threshold of appearing in at least half the frames and reaching amplitude 0.04 at least once.

Exact measured values and the track-map checksum are in `temporal-tracking-measurements.json`.

## Interpretation

The tracker can hold persistent identities for the two dominant sinusoids per channel in this test. The extra track IDs show that weaker spectral-pursuit components fragment; this is expected for a greedy local matcher and is an explicit limitation, not proof of source/instrument separation.

Default tracking does not modify KASF or Base samples. A separate `--experimental-track-refine` path changes serialized frequency/phase values and was found to reduce Base SNR on multiple synthetic test signals, so it is opt-in and excluded from the default pipeline.
