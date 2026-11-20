# KRM Prototype Architecture — Draft 0.6

- Package version: `0.6.0`
- Date: `2026-11-14`
- Physical KRM-IF: prototype revision `0.2`
- Native KASF FastGen: C++17 independent baseline
- Temporal tracking sidecar: `KASF-TrackMap-JSONL-v1`

## 1. Runtime pipeline

```text
Source PCM WAV
    │
    ▼
C++ FastGen baseline
    ├── periodic-Hann / radix-2 FFT peak analysis
    ├── sub-bin interpolation + weighted sine/cosine fit
    ├── quantized residual pursuit
    ├── KASF v1 writer (`KASF` magic)
    └── temporal ID association (sidecar only)
              │
              ├── KASF v1 file + metadata sidecar
              ├── KASF-TrackMap-JSONL-v1
              │
              ▼
       Native local Reader OLA
              │
              ▼
       KRM-PROTO-PCM-Q-v1
              │
              ▼
       Base integer PCM WAV
              │
Source PCM ───┴──► KRC: R = X - B
                         │
                         ▼
                     KRM-IF v0.2
                         │
                         ├── verify / restore
                         ├── streaming event probe
                         ├── streaming integer predictor
                         └── KRM-FC proposal data model
```

## 2. Temporal association

FastGen can associate each frame/channel component with a channel-local track ID. The map is a JSONL sidecar and its SHA-256 and row count are recorded in the metadata. It is not part of KASF v1 and is not needed by the Reader or KRC.

- Greedy is the default low-overhead local assignment.
- Hungarian is an optional per-frame global one-to-one minimum-cost assignment, capped at 256 active tracks and 256 current components per channel/frame.
- Both methods are metadata-only. KASF component bytes and native Base WAV bytes are identical when generation settings are identical.
- The experimental phase/frequency refinement is separate and can modify audio payload. It remains opt-in and is not considered a validated quality improvement.

Real-audio testing showed some reduction in track-ID fragmentation with Hungarian, but median tracks remained short. The system does not yet perform harmonic grouping, stereo linking, perceptual source tracking, or a multi-frame global model.

## 3. The three different equality checks

1. **Native Base vs Python reference Base:** renderer parity check. Byte identity means the two implementations produce the same experimental Base PCM.
2. **Source vs Base:** not expected to match. Their difference is the residual carried by KRM.
3. **Source vs Restored:** must match exactly after KRM adds the captured Raw Residual to Base. Real-audio bridge tests passed this condition for both tested WAV sources.

The equation remains:

```text
R[n,c] = X[n,c] - B[n,c]
X[n,c] = B[n,c] + R[n,c]
```

The `B` used by this prototype is still the local Reader OLA output plus `KRM-PROTO-PCM-Q-v1`. It is not an official full-application KASF PCM export and must not be labelled Canonical Base.

## 4. Measured real-audio results

Two existing Library WAVs were tested read-only: one mono 48 kHz source (8.66 s) and one stereo 44.1 kHz source (16.98 s). The Source/Base SNR values were 22.156 dB and 8.982 dB, respectively, showing that FastGen leaves substantial content for KRM residual storage. KRM-IF verification passed for both, and restored PCM was byte-identical to each Source.

Hungarian reduced created track IDs from 1,800 to 1,541 on the mono source and from 5,566 to 5,286 on the stereo source, at an added processing cost in the generator-only measurements. Greedy therefore remains default pending broader validation.

Detailed distributions and hashes are in `benchmarks/TRACKER-ASSIGNMENT-COMPARISON-Draft-0.6.md` and `benchmarks/real-audio-bridge-results-Draft-0.6.json`.

## 5. Current limits / next milestones

1. Improve component persistence using attack/decay handling, harmonic relationships, stereo coherence, and temporal confidence; keep tracking metadata-only until demonstrated otherwise.
2. Reproduce KASF's actual Source-domain decode, resampling, and channel mapping.
3. Compare the complete app-level final Reader/export path, including any official PCM quantization and normalization.
4. Only after 2–3 are established, promote an experimental Base profile to Canonical Base.
