# KRC — KRM Residual Capture Draft 0.1

Status: interface/algorithm draft plus partial Python prototype.

## Purpose

KRC obtains the final residual after KASF has completed its own representation/optimization path. It is intentionally separate from MRA's internal residual patches.

## Input contract

- `SourcePCM`: canonical source sample sequence.
- `BasePCM`: final output of the selected KASF Reader version after serialization, quantization, overlap-add, and defined normalization.
- `Timeline`: exact sample rate, sample count, channel count/order, sample format, and alignment mapping.

Source and Base must be mapped into the same integer PCM domain before subtraction.

## Core algorithm

For each sample and channel, compute using a wider signed integer type:

```python
residual = source_pcm - base_pcm
restored = base_pcm + residual
assert restored == source_pcm
```

The assertion must be checked across every sample and channel, not a probe subset.

## Required validation

- Source/Base rate, count, channel order, and format are compatible.
- Reader output is from the actual saved KASF representation.
- No hidden playback gain is included.
- The selected Reader normalization behavior is recorded.
- The integer difference does not overflow its storage type.
- Reconstruction does not clip.
- Block digests and whole-source digest match.

## Prototype behavior

`krm_proto capture` accepts two uncompressed PCM WAV files. It requires identical WAV parameters and rejects any mismatch. It does not execute a Reader, resample, normalize, or perform a channel/time projection. The supplied Base WAV must already be the canonical Reader PCM in the Source domain.

Supported WAV PCM widths: 8, 16, 24, 32 bits. WAV PCM8 is unsigned on disk and centered to signed values internally.

## Future KASF Adapter requirements

1. Obtain the exact final KASF byte representation.
2. Decode it with the selected Reader version.
3. Capture full-rate canonical PCM, not only sampled diagnostics.
4. Preserve global OLA/normalization semantics in chunked mode.
5. Provide sample alignment and channel mapping explicitly.
6. Compare streaming Reader and canonical Reader sample-for-sample.
7. Hand canonical Source/Base arrays to KRC.

## Not equivalent to MRA residual

MRA creates and modifies short local residual patches while improving components. KRC's Raw Residual is the final global difference between the complete Source and final Reader output. Local patches must not be concatenated or substituted for this final residual.
