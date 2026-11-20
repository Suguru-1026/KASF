# KRM Prototype Architecture — Draft 0.5

- Package version: `0.5.0`
- Date: `2026-11-14`
- Physical KRM-IF: prototype revision `0.2`
- Native KASF FastGen: C++17 baseline, version `0.1.0`

## 1. Runtime pipeline

```text
Source PCM WAV
    │
    ▼
C++ FastGen baseline
    ├── periodic-Hann / FFT peak analysis
    ├── sub-bin interpolation + weighted sine fit
    ├── quantized residual pursuit
    └── KASF v1 writer (`KASF` magic)
              │
              ├── KASF v1 file + metadata sidecar
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

## 2. Responsibilities

- **FastGen:** independent fast KASF v1 baseline encoder. Does not rewrite the user's KASF HTML/source or claim full Rev.0.9.20 algorithm parity.
- **Reader bridge:** renders quantized KASF components through the local Reader OLA equation, retaining the actual frame/hop rounding rules and using guard crop when enabled.
- **KRC:** captures integer Source/Base pair, computes exact signed int64 residual, hashes and checkpoints blocks.
- **KRM Core:** analyzes the residual without changing the authoritative stored data.
- **KRM-IF:** stores Base and Raw Residual separately from optional analysis data.
- **KKI/KRM-FC:** remain interface and candidate proposals; no KASF transaction manager or KASF-side integration is implemented.

## 3. Trust and status labels

`canonical_kasf_export` must remain `false` for FastGen-produced Base. The local Reader formula comparison is very close to the actual Rev.0.9.20 JavaScript implementation, and native/Python PCM parity passed, but the complete app-level post-processing and official PCM quantization pipeline remain unresolved.

KRC exactness is narrower and already established: for any accepted integer Source/Base pair, `R = X - B` and `X = B + R` are exact in the declared PCM integer domain. This remains true whether Base is official KASF output, FastGen prototype output, or another explicitly identified producer.

## 4. Next technical milestones

1. Reproduce KASF's actual Source-domain decode and optional resampling/channel mapping.
2. Exercise full app-level final Reader/export path and compare on silence, transients, sustained tones, odd frame geometry, multiple channels, and phase-connected worker seams.
3. Determine the authoritative PCM quantization / normalization policy if an official export exists.
4. Improve FastGen with temporal component tracking, transient model, and phase continuity without conflating those research steps with KRC exactness.
5. Only after 1–3 are established, allow a KRM Base profile to be promoted from experimental to canonical.
