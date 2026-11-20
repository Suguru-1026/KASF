# KRM Analysis Pipeline Review — Draft 0.1

Status: research review and staged work plan. Not a formal version release.

## 1. Baseline recovered from Draft 0.8

The existing integrated design separates three data roles:

1. `RAW_RESIDUAL`: authoritative exact reconstruction data.
2. `ANALYSIS_REPRESENTATION`: derived diagnostics that can be regenerated or deleted.
3. `PREDICTIVE_REPRESENTATION`: experimental model state plus exact innovation data.

The documented residual-side analysis route is:

1. broad pre-analysis (amplitude, energy, time variation, channel correlation, broad spectral structure);
2. HPSS/STN structural guidance;
3. MP/chirplet event discovery;
4. selective detailed analysis (EMD/HHT, VMD, Wavelet, SST);
5. feature fusion;
6. KRM-FC proposal generation only where KASF representability is plausible.

The integrated design explicitly says an MP atom is not automatically one semantic/acoustic event. Multiple atoms may form one event, and event termination requires explicit segmentation/tail estimation.

## 2. Confirmed implementation boundaries

- `events.py` is a coarse RMS/peak/ZCR activity probe. Its automatic threshold uses recording-wide median frame RMS times a multiplier, bounded by an absolute floor.
- `tea.py` is a separate local time-domain transient/activity candidate detector. It is not a replacement for `events.py`.
- `candidates.py` validates KRM-FC metadata. It does not prove a proposal is acoustically correct or representable in KASF.
- KRM-IF Analysis/Events blocks are optional and must not be needed to restore audio.
- KKI requires algorithm/version and parameter provenance for proposals, as well as parent revision identity.
- The local FastGen/Reader bridge is not the canonical final KASF Reader path. Its output must not be used as if it were official final Reader PCM.

## 3. External onset-detection research

A standard onset-detection design separates:

1. a detection function / novelty curve that measures change;
2. a later peak-picking or event-decision stage.

This is important for KRM: a spectral novelty value is evidence of change, not by itself an acoustic event or a KRM-FC proposal.

Relevant method families:

- **Spectral Flux:** positive spectral-magnitude increase between frames; useful as a simple spectral-change baseline.
- **HFC (High Frequency Content):** frequency-weighted spectral content, often responsive to percussive attacks.
- **Complex-domain difference:** combines magnitude change with phase deviation from expected frame evolution.
- **Mel Flux / bandwise flux:** aggregates changes in perceptually spaced bands.
- **RMS difference:** energy-change baseline; overlaps conceptually with the time-domain family and should not be mistaken for a full spectral descriptor.

No single ODF is universally best. Different methods respond differently to percussive and tonal events, so KRM should preserve independent proposal channels and compare them on labelled residual excerpts.

## 4. Recommended channel boundaries

| Channel | Proposed responsibility | Must not claim |
|---|---|---|
| `events.py` | Broad energy-activity regions | Transient identity or semantic event |
| TEA | Time-domain abrupt-change / isolated-peak candidates | Exact onset, transient class, musical-noise diagnosis |
| MTA | Temporal candidate-region analysis | Its precise contract is not yet recovered in Draft 0.8 |
| Spectral Novelty | Frame-to-frame spectral-change proposals | Confirmed event or source classification |
| MP / Chirplet | Local atom and time-frequency event descriptors | One atom = one physical event |
| EMD/HHT, VMD, Wavelet, SST | Selected-region detailed analysis | Universal decomposition or guaranteed source separation |
| KRM-FC | Candidate proposal to KASF | Accepted/committed KASF component |

### Recovered prior decisions (2026-11-14)

The earlier conversation records these decisions and prototype results. They are prior assistant-reported work, not independently reproduced in this working copy:

- MTA is a time-domain energy-change candidate-region detector. Its recorded feature family was Short RMS, Long RMS, RMS Ratio, Envelope Slope, Crest Factor, ZCR, and Difference Energy. The RMS ratio was tested in two forms: central ratio `Rc = ShortRMS / surroundingLongRMS`, and prior ratio `Rp = ShortRMS / priorLongRMS`. When no prior frame exists, `past_energy_ratio` must be set to 0 rather than divided by a tiny denominator; this was an explicit first-frame false-positive fix.
- Recorded MTA window/ratio sweeps included Short/Long/ratio = 32/256/1.8 and 64/512/1.8 (both 7/7 in a small initial test), while 128/1024/1.8 produced 6/7. The 32/256/1.8 profile was only a tentative candidate, not a frozen standard. The hop size and exact formulas/thresholds for Envelope Slope, Difference Energy, and Crest Factor are not recoverable from the archived ZIP or retrieved history.
- MTA feature ablation was reported on 32 events plus negative examples over four random seeds: central RMS ratio P=83.3%, R=62.5%, F1=0.714; prior-energy ratio P=100%, R=75.0%, F1=0.857; Envelope Slope P=90.0%, R=56.2%, F1=0.692; Difference RMS P=100%, R=28.1%, F1=0.439; Crest Factor P=57.7%, R=46.9%, F1=0.517; all-feature OR P=68.6%, R=75.0%, F1=0.716 with 11 false positives. These are reported historical synthetic results, not current reproduced measurements. The prior-energy ratio was the strongest individual feature in that test; naive OR fusion was worse due to false positives.
- The recorded synthetic cases included isolated/single transients, unequal-amplitude transient sequences, transients under sustained noise, dense transient groups, periodic-plus-transient overlap, overlapping transients, nonstationary sustained noise, constant-volume frequency changes, short noise attacks over a sustained tone, steady tones, noise bursts, and gradual same-frequency level rises. Gradual level rises were reportedly missed by both MTA and Spectral Novelty in one comparison.
- Spectral Novelty uses Positive Spectral Flux:

  ```text
  SF_t = sum_k(max(M[t,k] - M[t-1,k], 0))
         / max(sum_k(M[t,k]), sum_k(M[t-1,k]))
  ```

  A zero denominator needs an explicit zero-output rule. The earlier synthetic prototype used Hann + FFT, mono/offline processing, a 512-sample window, 32-sample hop, and threshold 0.035. A 256-sample window caused stationary-tone false positives in one test; 512 did not. These are test-specific settings, not general defaults or proven optima.
- Architecture A: independent MTA and Spectral Novelty proposal channels, followed by downstream overlap/nearby-region association. One-sided candidates are retained; neither detector vetoes the other.
- Architecture B: mutual reference/evidence correction. Initial B-2/B-3 prototypes did not improve the tiny synthetic detection score over A and remain exploratory.
- Architecture C: hierarchical MTA-gated Spectral Novelty. It was not selected as the baseline because a gate can prevent the second detector from seeing events missed by the first.
- A proposed common `EventCandidate` shape included `start_sample`, `end_sample`, `source_method`, `confidence`, `energy_change`, `spectral_change`, and `feature_data`. This remains a proposed shared envelope, not an archived frozen schema.

The earlier local prototype was reported as reaching 74/74 tests for MTA, then 80/80 and 85/85 during subsequent fusion experiments. A tiny synthetic comparison was reported as MTA 2 correct / 2 missed / 0 false; Spectral Novelty and A/B variants 3 correct / 1 missed / 0 false. The sample count is too small to establish a general performance advantage. Crucially, the only archived Library package remains Draft 0.8; the MTA/Spectral Novelty source, benchmark, and later tests were left in an unarchived local working copy and are not present in the current ZIP or runtime filesystem.

Therefore, do not treat the prior 74/74, 80/80, or 85/85 counts as tests of the current worktree. The current 78-test run covers Draft 0.8 plus the present TEA changes only.

The previously selected MTA + Spectral Novelty Architecture A remains the reference: separate proposal channels, then downstream association. Cross-referencing (Architecture B) remains research-only. TEA must remain independently identifiable until its placement is decided with evidence. Because MTA already occupies the time-domain energy-change role, the next comparison must be TEA vs MTA, not merely TEA vs `events.py`.

## 5. Spectral Novelty baseline contract — proposed, not implemented

Before implementation, freeze these choices:

- input domain and channel policy;
- FFT size, hop, window, centering and boundary padding;
- magnitude, power, or log-magnitude domain;
- positive-only or signed spectral difference;
- frequency-axis local maximum filtering (if used);
- frequency aggregation (mean, median, weighted bands);
- per-channel versus joint-stereo computation;
- novelty-curve smoothing and peak-picking kept as separate stages;
- sample-index mapping and algorithm/parameter provenance.

The earlier KRM prototype already selected the positive-flux expression above. Rebuild that baseline faithfully before trying alternatives. A local-frequency-maximum reference variant, HFC, and complex-domain ODFs can follow as separate optional methods. Do not silently replace the previous formula or fuse methods into one opaque score.

## 6. Validation protocol

### Synthetic labelled data

Include silence, stationary tone, stationary noise, amplitude steps, slow attacks, short impulses, decaying transients, repeated transients, chirps, mixed tones, stereo-correlated events, and events masked by a louder steady component. Vary sample rate, gain, and noise floor.

### Metrics

- event recall and precision at explicit onset tolerances;
- false positives per minute on negative/control signals;
- onset localization error in samples and milliseconds;
- interval coverage / overlap for interval detectors;
- performance by event class, level, and channel condition;
- runtime and peak memory;
- sensitivity to parameter changes.

Do not compare detectors with incompatible targets using one raw candidate count. `events.py` activity intervals and TEA onset-like candidates describe different things.

### Real residual gate

Only test real KRM residual behavior when the exact pair is available:

- canonical Source PCM `X`;
- actual final KASF Reader PCM `B` from the same saved KASF revision;
- verified `R = X - B`;
- matching timeline/channel/sample metadata.

A source WAV alone is not a residual. A local FastGen baseline is not a substitute for the official final Reader path.

## 7. Staged Draft 0.9 plan

1. Stabilize TEA and prove chunked/in-memory equivalence; measure bounded-memory behavior.
2. Reconstruct the prior MTA implementation from the recorded feature family and prior-energy ratio result. Treat missing hop, feature formulas, and thresholds as unresolved; any choices made during reconstruction must be explicitly marked new.
3. Compare TEA vs MTA vs `events.py` on the same labelled fixtures to establish overlap and unique detections.
4. Rebuild the prior Positive Spectral Flux baseline using the recorded formula; keep the 512/32/0.035 settings as one synthetic test profile only.
5. Reproduce Architecture A with separate detector outputs and one-sided candidate retention before testing B/C.
6. Build broader labelled synthetic evaluation and parameter-sensitivity reports.
7. Add provenance-compatible event records and KRM-IF/KKI mapping without changing Raw Residual payload.
8. Run real-residual validation only after the canonical KASF Reader adapter is available.
8. Keep exact restoration tests as a release gate; no analysis module may alter the exact layer.

No formal Draft 0.9 release should be declared until these gates and release metadata are complete.

## References

- Bello, J. P., Daudet, L., Abdallah, S., Duxbury, C., Davies, M., & Sandler, M. (2005). *A Tutorial on Onset Detection in Music Signals*. IEEE Transactions on Speech and Audio Processing. DOI: 10.1109/TSA.2005.851998.
- Essentia documentation, *Onset detection* tutorial and `OnsetDetection` reference. Describes ODF computation followed by a separate onset decision stage; includes HFC and complex-domain examples.
- librosa 0.11 documentation, `librosa.onset.onset_strength`. Defines spectral-flux onset strength as positive spectral change relative to a locally max-filtered reference.
