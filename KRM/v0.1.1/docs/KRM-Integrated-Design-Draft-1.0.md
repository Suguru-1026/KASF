# KRM Integrated Design Draft 1.0

Date: 2026-11-14  
Status: design baseline; implementation is partial and experimental.

## 1. Objective

KRM is an independent residual-analysis and residual-representation system that cooperates with KASF. Its purpose is not merely to remove noise. It handles audio information that the current KASF representation captures with insufficient accuracy, efficiency, or stability.

Primary priority: **reconstruction fidelity first**. Compression is explicitly not a first-version goal.

## 2. Core signal model

Let:

- `X[n,c]`: canonical source PCM, sample index `n`, channel `c`.
- `B[n,c]`: canonical KASF Reader output aligned to the source PCM domain.
- `R[n,c]`: Raw Residual.

```text
R[n,c] = X[n,c] - B[n,c]
X[n,c] = B[n,c] + R[n,c]
```

For integer PCM, the addition must be performed in a sufficiently wide signed integer type. Clipping is forbidden during residual addition. If the reconstructed value exceeds the declared source PCM range, verification fails.

The canonical source is the decoded PCM representation selected by the KRC input contract. For lossy-source formats, the guarantee applies to that decoded PCM, not to the original compressed-file bitstream.

## 3. Responsibility split

### KASF

- Generator: initial component extraction.
- KASE-2.1: optimization/search of existing component parameters in its applicable path.
- MRA 0.9: Reader-residual analysis and localized component add/replace/delete/refit.
- Reader v1.2: canonical synthesis from saved KASF v1 representation.

KRM must not duplicate these stages without a demonstrated need. Existing KASF source audit indicates that MRA already searches quantized Reader residuals and makes localized component changes, but it does not persist the complete residual PCM.

### KRM

- KRC: capture final residual PCM.
- KRM-IF: hold Base, Raw Residual, metadata, analyses, events, candidates, and integrity data.
- KRM Core: residual analysis and alternate representations.
- KRM-SIM: research-only state-based predictor candidate.
- KRM-FC: frequency/event-derived candidate proposal format for KASF.

### KKI

KKI is the exchange protocol between KASF and KRM. It carries signal references, analysis metadata, frequency candidates, evaluation results, revision identity, and acceptance status. It does not expose or mutate either engine's internal data structures directly.

## 4. KRC (KRM Residual Capture)

KRC runs only after the final KASF data has been saved and the canonical Reader output has been generated.

Required inputs:

1. Canonical source PCM.
2. Canonical Reader PCM generated from the saved KASF representation using the target Reader version and its actual synthesis/normalization path.
3. Explicit sample-rate, sample-count, channel, and PCM-format metadata.

KRC must not use unquantized Generator components or a theoretical sinusoidal sum as the Base. It must use the actual Reader result.

KRC outputs:

- Base PCM reference or snapshot.
- Raw Residual PCM.
- Source/Base digests.
- Timing/channel mapping metadata.
- Exact-reconstruction verification result.

The first prototype accepts only matching Source and Base WAV metadata. A future KASF Adapter must implement and test reader-forward output capture, global normalization, resampling, channel mapping, delay compensation, and streaming equivalence before claiming full KASF support.

## 5. KRM-IF layers

| Layer | Purpose | Required? |
|---|---|---|
| Header / Manifest | Identity, version, session, revision | Yes |
| Timeline / Source Metadata | Rate, length, channels, PCM format | Yes |
| Base Signal | Canonical Reader output | Yes for standalone restore |
| Raw Residual | Exact integer difference | Yes |
| KASF Reference | KASF file/Reader/config identity | Yes in KASF-linked sessions |
| Analysis | HPSS, STN, MP, EMD, HHT, VMD, Wavelet, SST, etc. | No |
| Tracking | Track IDs, trajectories, lifetimes | No |
| Events | Onset, duration, frequency behavior, confidence | No |
| Candidates | KRM-FC proposals and states | No |
| Integrity / Journal | Checksums, hashes, process history, commit data | Integrity yes; journal required for resumable production builds |

Analysis data is never required to restore audio. Deleting an analysis block must not affect `Base + Raw Residual` reconstruction.

## 6. Residual and analysis representations

Three concepts remain distinct:

1. `RAW_RESIDUAL`: authoritative exact reconstruction data.
2. `ANALYSIS_REPRESENTATION`: derived diagnostic data (e.g. HPSS masks, MP atoms, IMFs, instantaneous-frequency tracks).
3. `PREDICTIVE_REPRESENTATION`: model state and exact innovation data from predictor experiments.

Derived data must include provenance: algorithm ID/version, parameters, input signal/revision, sample range, and output encoding. Derived data may be regenerated or discarded.

## 7. Analysis pipeline

The proposed residual-side flow is:

1. Pre-analysis: amplitude, energy, time variation, channel correlation, broad spectral structure.
2. Structural guidance: HPSS/STN features (classification/guidance, not assumed to be a complete source separator).
3. Event discovery: Matching Pursuit and chirplet-like analysis to estimate onset, duration, center frequency, chirp rate, amplitude envelope, bandwidth, phase, and confidence.
4. Detailed analysis: EMD/HHT, VMD, Wavelet, SST, or other methods selected according to the residual region.
5. Feature fusion: associate atoms/modes/tracks with higher-level audio events.
6. Candidate generation: create KRM-FC only where the event appears representable by KASF components.

An MP atom is not assumed to equal one semantic/acoustic event. Multiple atoms may be merged into one event, and event termination requires explicit segmentation/tail estimation.

## 8. KRM-SIM

KRM-SIM (State-based Innovation Modeling) is a research hypothesis, not a finalized codec or required decoder component.

```text
predicted_residual[n] = F(state[n], residual_history)
innovation[n] = residual[n] - predicted_residual[n]
residual[n] = predicted_residual[n] + innovation[n]
```

State candidates include time-varying spectral distribution, amplitude and rate of change, AM/FM behavior, band correlations, stereo relationships, event lifecycle, and decay properties.

Raw Residual remains authoritative. The initial implementation must not depend on predictor correctness.

## 9. KRM-FC and KKI candidate lifecycle

KRM-FC represents a proposal, not a confirmed KASF component. A candidate should identify its parent KASF revision and parent residual revision to avoid stale proposals.

Recommended lifecycle:

`PROPOSED → RECEIVED → PREFLIGHT → STAGED → SYNTHESIZING → QUALITY_CHECK → KRM_VERIFY → COMMITTED`

Failure branches:

- `REJECTED`: preflight or quality policy rejects the proposal.
- `ROLLED_BACK`: a staged trial or verification fails; prior committed state is retained.

KASF should:

1. Check candidate validity and representability.
2. Stage the proposal on a trial copy.
3. Optionally optimize applicable component parameters using existing KASF tools.
4. Quantize and serialize through the actual KASF v1 path.
5. Run the actual Reader.
6. Evaluate waveform/spectral/envelope/attack safeguards.
7. Request a fresh KRC capture for the trial output.
8. Commit only after exact reconstruction and integrity checks pass.

Approximate resynthesis may rank proposals but must not authorize final acceptance.

## 10. Revision / transaction policy

KASF and KRM states are immutable per revision. No trial operation overwrites the prior committed Base or Residual.

For a trial revision:

- write candidate KASF output;
- produce trial Base;
- produce trial Raw Residual;
- validate each chunk and the whole output;
- verify `Base + Residual == Source` for every sample/channel;
- verify manifest and block integrity;
- atomically change the committed manifest/reference only after all checks pass.

On failure, retain the previous committed revision. KASF and KRM revisions must never be committed independently.

## 11. Long-recording policy

The intended production direction is chunked, bounded-memory processing with a journal and resumable checkpoints. Reader overlap-add state and global normalization must remain equivalent to the canonical whole-signal Reader. A streaming path is not considered correct until sample-for-sample compared with the canonical Reader.

The current Python prototype writes a complete temporary `.partial` file then renames it. It does not yet implement crash resume or a production journal.

## 12. Performance context

A user-reported calculated estimate for one workload improved from approximately 55 hours at KASF Rev.0.9.7 to approximately 26 hours at Rev.0.9.20. This has not been independently benchmarked in the KRM package. KRM should avoid repeating KASF analysis/optimization and instead spend compute on residual-specific work.

## 13. Out of scope for Draft 1.0

- Lossy residual coding.
- Entropy coding/compression optimization.
- Full KASF runtime integration.
- Full HPSS waveform separation.
- Full canonical Matching Pursuit/Chirplet engine.
- Production KRM-SIM.
- Production cross-engine transaction coordinator.
- Bit-exact preservation of original lossy-compressed file bytes.
- Float PCM bit-pattern identity.

## 14. Prototype boundary

The accompanying Python prototype tests only an integer-PCM Source/Base pair, exact residual creation, chunk integrity, restoration, predictor reversibility, coarse event probing, and candidate metadata validation. It does not run KASF Reader and cannot certify the real KASF output path.
