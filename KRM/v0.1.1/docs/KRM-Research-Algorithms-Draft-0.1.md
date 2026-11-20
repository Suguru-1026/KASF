# KRM Research Algorithms Draft 0.1

Status: research map plus small baseline experiments. No claim that the listed research algorithms are implemented in the package.

## 1. Separation of roles

### Exact layer

The exact layer stores `Raw Residual` and is independent of predictor/analysis success.

### Analysis layer

The analysis layer describes signal structure. It may be lossy, approximate, revisable, or deletable without affecting PCM reconstruction.

### Predictive layer

The predictive layer attempts to model residual behavior and preserve exact innovations. Predictive success is not a prerequisite for restoration.

## 2. Candidate methods

| Method | Intended KRM role | Caveat |
|---|---|---|
| HPSS | Harmonic/percussive structural guidance | Not equivalent to KASF representability; KASF's current HPSS path is analysis guidance, not full separation. |
| STN | Soft sinusoidal/transient/noise attributes | Classification is not a full decomposition. |
| Matching Pursuit | Local atom/event discovery | Atoms are not automatically one-to-one with audio events. |
| Chirplet analysis | Frequency-varying event description | Dictionary design and event merging need validation. |
| EMD/HHT | Nonstationary mode and instantaneous-frequency analysis | Mode mixing, end effects, noise sensitivity, and low-amplitude IF instability. |
| VMD | Controlled mode decomposition | Requires choices about mode count and penalty parameters. |
| Wavelet | Local time-scale structure | Results depend on wavelet and scale selection. |
| SST | Sharpened time-frequency representation | Needs careful treatment of multicomponent/low-energy regions. |

The planned first route is broad characterization followed by selective detailed analysis, rather than running every expensive method on every sample.

## 3. Event record

An event is a higher-level acoustic description, distinct from a mathematical atom or an IMF.

Candidate fields:

- onset sample / end sample (exclusive)
- duration
- center frequency and frequency trajectory
- chirp rate
- amplitude envelope and decay
- phase reference
- bandwidth
- channel/stereo relation
- confidence and uncertainty
- source atom/track IDs

Event merging and termination are separate operations. Multiple MP atoms may describe one event; one event may also be represented by several analysis methods.

## 4. Integer predictor baselines in this package

`predictor.py` implements two reversible integer predictors:

Order 1:

```text
prediction[n] = residual[n-1]
innovation[n] = residual[n] - prediction[n]
```

Order 2:

```text
prediction[n] = 2*residual[n-1] - residual[n-2]
innovation[n] = residual[n] - prediction[n]
```

The first one or two residual samples are seeds. Decoder uses identical integer arithmetic:

```text
residual[n] = prediction[n] + innovation[n]
```

The implementation proves exact reversibility for these predictors, but it does not bit-pack innovations, entropy-code them, or claim compression. Integer innovations can require more bits than the original residual samples.

## 5. KRM-SIM research hypothesis

KRM-SIM may augment history-based prediction with a state vector containing:

- local spectral-energy distribution
- amplitude and its rate of change
- AM/FM trends
- band-to-band correlation
- stereo relationship
- event lifecycle and decay state

Potential structure:

```text
prediction[n] = F(state[n], residual_history)
innovation[n] = residual[n] - prediction[n]
```

For an exact path, the innovation must be stored as an exact integer and all state evolution needed by the decoder must be reproducible. This package does not implement KRM-SIM.

## 6. Coarse event probe in this package

`events.py` calculates frame RMS, peak magnitude, and zero-crossing rate. Its optional threshold uses:

```text
max(absolute_floor, median(frame_rms) * baseline_multiplier)
```

Adjacent active windows are merged. The result is named `energy_activity_candidate`, not a validated acoustic event. It does not estimate frequency, chirp, phase, source class, or MP atoms.

## 7. KRM-FC validation in this package

`candidates.py` validates basic metadata:

- finite numeric fields
- valid sample interval
- center frequency within Nyquist
- non-negative amplitude/bandwidth
- confidence in `[0,1]`

It does not quantize to KASF's 48-bit Component fields or perform Reader-forward evaluation.

## 8. Planned research comparisons

1. Direct residual baseline.
2. DPCM order 1 and 2 predictor baselines.
3. LPC predictor (future).
4. KRM-SIM state predictor (future).
5. MP/Gabor/Chirplet event extraction (future).
6. EMD/HHT vs VMD vs Wavelet/SST on selected residual regions (future).

Evaluate exact PCM equality separately from predictive error, event precision/recall, spectral fit, execution time, and memory. Exact restoration must remain 100% even when an analysis model fails.
