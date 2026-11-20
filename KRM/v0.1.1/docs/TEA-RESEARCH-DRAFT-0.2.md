# KRM Transient Event Analysis (TEA) — Research Draft 0.2

Status: experimental analysis component. This is not a formal KRM Draft 0.9 release.

## 1. Role and boundary

TEA is a time-domain proposal channel for short-lived or rapidly changing activity in the Source-domain Raw Residual. It is not the global energy-activity detector, not MTA, and not Spectral Novelty.

TEA reads a view/copy of Raw Residual and emits derived measurements and candidate intervals. It MUST NOT modify, quantize, filter, normalize, replace, or become a prerequisite for the authoritative Raw Residual stored by KRC/KRM-IF.

The exact path remains:

```text
R[n,c] = X[n,c] - B[n,c]
X[n,c] = B[n,c] + R[n,c]
```

Deleting TEA output or failing TEA analysis must have no effect on exact restoration.

## 2. Draft 0.2 implementation

Implementation: `krm_proto/tea.py` (`KRM-TEA-TD-Candidate-v0.2`). Standard library only.

Frame measurements:

- RMS
- peak absolute amplitude
- mean absolute amplitude
- crest factor
- preceding-frame median RMS
- RMS rise ratio
- candidate reason flags

A frame is a candidate when it clears the configured absolute RMS floor and either:

1. RMS relative to the preceding-frame median reaches `rise_ratio_threshold`; or
2. crest factor reaches `crest_factor_threshold`.

Candidate frames are merged according to `merge_gap_frames`. The returned interval is the union of selected frame intervals. It is a frame-grid-expanded candidate interval, not a precise physical transient boundary or onset timestamp.

### Numerical handling

Frame RMS and mean absolute value are computed after scaling by the maximum absolute sample in the frame. This avoids intermediate square/sum overflow for large finite floating-point values. Non-finite values, booleans, invalid geometry, and invalid thresholds are rejected.

### Long-recording path

`iter_transient_candidates_from_chunks(...)` consumes chunks and yields closed candidate records without retaining the complete recording, every frame record, or all prior events. It retains bounded frame carryover, the configured preceding-frame history, and the currently open candidate. Its event records are tested for exact equality with the in-memory API across irregular chunk boundaries and `hop_samples > window_samples`.

The in-memory `detect_transient_candidates(...)` remains useful for short fixtures and diagnostic frame output, but it retains all frame records and should not be selected by default for long recordings.

### Provenance

Each event record carries:

- `detector_id`: `KRM-TEA-TD-Candidate-v0.2`
- exact parameter values used
- event ID and frame indices
- candidate reasons
- `confidence: null`

This is a detector output, not a calibrated probability. KRM-IF Analysis metadata and KKI exchange metadata must retain algorithm/version, parameters, input revision, sample range, and channel identity when integrated.

## 3. Research interpretation and limits

The literature distinguishes an attack interval, a transient interval, and an onset instant. TEA currently does not estimate those concepts separately. It identifies frame intervals whose simple time-domain measurements changed enough to merit further analysis.

Important limitations:

- A candidate is not proof of a physical transient.
- TEA does not identify musical noise, instruments, impacts, clicks, or semantic sound classes.
- Crest factor can respond to isolated noise or quantization spikes.
- RMS rise depends on window, hop, preceding history, gain, and residual scale.
- Overlapping windows are correlated measurements, not independent observations.
- If `hop_samples > window_samples`, merged frame intervals can span unmeasured gaps; the interval is a coarse support range.
- The first frame has no preceding history and can only qualify through crest factor.
- There is no stereo coupling, learned threshold, calibrated confidence, or MTA fusion.
- No actual canonical KASF final-Reader Raw Residual has yet been validated.

For production KRM integration, the expected input is the canonical integer Raw Residual from KRC. Any transformed or normalized analysis view must be separately declared in provenance; the authoritative residual itself remains unchanged.

## 4. Relation to other KRM analysis channels

- `events.py`: coarse energy-activity baseline; keep it separate.
- TEA: time-domain transient/activity proposals; keep detector identity and reasons.
- MTA: previously discussed as a temporal candidate-region detector; exact implementation contract still needs to be recovered/confirmed.
- Spectral Novelty: a separate spectral-change proposal channel. Literature supports using onset-detection functions as intermediate novelty curves, followed by a separate peak/event decision stage.
- Matching Pursuit / Chirplet: later event/atom description, not equivalent to frame-level TEA candidates.
- EMD/HHT, VMD, Wavelet, SST: selective detailed analysis, not unconditional processing of all residual samples.

The earlier architecture decision to keep MTA and Spectral Novelty as parallel proposal channels (Architecture A) remains the reference. Their outputs should be associated downstream; one channel must not silently veto another. TEA's exact placement relative to MTA remains unresolved and must not be guessed.

## 5. Validation

The TEA unit tests cover:

- known frame metrics;
- isolated impulse response;
- constant-level and silence rejection;
- candidate merging;
- non-finite input rejection;
- invalid parameter rejection;
- stable metrics for large finite values;
- streaming/in-memory equivalence over irregular chunks;
- streaming/in-memory equivalence when hop exceeds window;
- empty streaming input.

The full prototype test suite currently reports 78 passing tests in the development environment. This is software-behavior validation, not real-audio detection accuracy.

A separate `tracemalloc` check on a generated 10-second, 48 kHz mono signal (1024-sample window, 256-sample hop, 8192-sample streaming chunks) measured 4,766,032 bytes peak Python allocation for the batch path and 223,004 bytes for the chunked path; both emitted 9 candidate records. The batch call creates and retains the full input list inside the measured call, while streaming generates chunks on demand; the difference therefore reflects the end-to-end usage pattern, not isolated detector overhead. This is an environment-specific Python-allocation measurement, not process RSS, runtime, or a general memory guarantee.

## 6. Next experiments

1. Build a labelled synthetic suite with positive and negative cases, multiple gains, noise floors, transient durations, attack slopes, and stereo relationships.
2. Report event recall, false positives per minute, onset localization error, and interval coverage separately. Do not optimize raw candidate count.
3. Compare parameter stability over sample rate, PCM width, gain, and window/hop choices.
4. Add a separate Spectral Novelty baseline (initially spectral flux) only after its FFT/window/boundary/channel contract is fixed.
5. Compare TEA and Spectral Novelty as independent channels before any fusion.
6. Validate on actual KASF residuals only when both canonical Source PCM and the actual final Reader Base PCM from the same revision are available.
7. Preserve the KRC/KRM-IF exact-residual path unchanged.
