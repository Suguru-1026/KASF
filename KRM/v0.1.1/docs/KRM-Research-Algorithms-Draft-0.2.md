# KRM Research Algorithms Draft 0.2

Status: research map plus executable, deliberately simple baselines. No claim that canonical MP, HPSS, EMD/HHT, VMD, SST, or KRM-SIM are implemented.

## 1. Three strictly separated signal/data roles

### Exact layer

The exact layer stores Base PCM plus Raw Residual. It is the only authority for exact reconstruction.

### Analysis layer

The analysis layer describes residual structure. It may be approximate, revised, or deleted without affecting reconstruction.

### Predictive layer

The predictive layer models residual values and exact innovations. It is an experiment; prediction quality is not a restoration precondition.

## 2. Analysis method map

| Method | Intended role | Caveat |
|---|---|---|
| HPSS | Harmonic/percussive structural guidance | Not equivalent to KASF representability; no full separation is implemented here. |
| STN | Sinusoidal/transient/noise-like attributes | Soft classification is not full decomposition. |
| Matching Pursuit | Local atom/event discovery | Atoms are not automatically one-to-one with acoustic events. |
| Chirplet | Frequency-varying event description | Dictionary design and event merging need validation. |
| EMD/HHT | Nonstationary modes and instantaneous frequency | Mode mixing, end effects, noise sensitivity, and low-amplitude IF instability. |
| VMD | Controlled mode decomposition | Mode count and penalty parameters require selection. |
| Wavelet | Local time-scale structure | Results depend on wavelet and scale choices. |
| SST | Concentrated time-frequency representation | Multicomponent and low-energy regions need careful treatment. |

The intended route is broad characterization followed by selective detailed analysis, not unconditional execution of every expensive method on every sample.

## 3. Event and atom distinction

An Event is a higher-level acoustic description, distinct from an MP atom, chirplet, FFT peak, or IMF. Multiple atoms may describe one event, and multiple analysis methods may contribute to one event.

Candidate event fields include onset/end samples, duration, center-frequency trajectory, chirp rate, amplitude envelope, phase reference, bandwidth, channel relation, confidence/uncertainty, and source atom/track IDs.

## 4. Executable baselines in Draft 0.2

### Integer prediction

`predictor.py` implements reversible order-1 and order-2 integer prediction. `verify_predictive_chunks()` demonstrates continuity across chunk boundaries. No entropy coding or compression is performed.

### Energy activity probe

`events.py` provides RMS, peak, and zero-crossing-rate frame features. Streaming frame extraction retains only the current window's carryover. For automatic thresholding, the CLI performs two passes and estimates median frame RMS using the constant-memory P² algorithm.

The P² median is approximate. Events are labeled `energy_activity_candidate`; the probe does not detect source classes, chirp events, MP atoms, or separated waveforms.

### KRM-FC data model

`candidates.py` validates:

- candidate sample interval and phase-reference sample;
- finite frequency/amplitude/phase/chirp/bandwidth/confidence;
- Nyquist and bandwidth boundaries;
- source event and parent revision identifiers;
- ordered per-frame/per-channel `ComponentProposal` records.

This remains a metadata contract only. There is no KASF 48-bit quantizer mapping or Reader-forward acceptance code.

## 5. KRM-SIM research hypothesis

KRM-SIM may supplement history-only prediction with a state vector containing local spectral-energy distribution, amplitude/rate, AM/FM trends, band correlations, stereo relationship, event lifecycle, and decay state.

```text
prediction[n] = F(state[n], residual_history)
innovation[n] = residual[n] - prediction[n]
residual[n] = prediction[n] + innovation[n]
```

For any eventual exact path, the innovation must be stored as an exact integer and decoder state evolution must be reproducible. The prototype does not implement KRM-SIM.

## 6. Planned comparisons

1. Direct Raw Residual baseline.
2. DPCM order 1 and 2.
3. LPC predictors.
4. KRM-SIM state predictor.
5. Gabor MP and Chirplet event descriptors.
6. EMD/HHT versus VMD versus Wavelet/SST on selected residual intervals.

Track exact PCM equality separately from prediction error, event precision/recall, spectral fit, runtime, and memory. The exact path must remain 100% sample-identical even when analysis models fail.
