# KASF Reader Adapter Contract — Draft 0.3

Status: source-audited integration contract; adapter implementation is not included.

Audit target: `KASF-2.0-Evolution-Rev0.9.20-Temporal-Guards.html` from the user's KASF Rev.0.9.20 source package. This document distinguishes behavior directly visible in that source from requirements that still need to be established by the canonical standalone Reader.

## 1. Why this contract exists

KRC must capture the actual Base waveform represented by the final saved KASF file. A sum of unquantized components, an optimizer's local approximation, a Worker output before the chunk join, or browser playback output is not an acceptable substitute.

The KRM equation remains:

```text
R[n,c] = X[n,c] - B[n,c]
X[n,c] = B[n,c] + R[n,c]
```

`X` and `B` must be integer PCM in exactly the same sample domain, channel order, sample count, and quantization convention.

## 2. KASF v1 layout verified in Rev.0.9.20

### 32-byte header

The source's `KASF_CHUNKS.header()` writes the following little-endian fields:

| Offset | Width | Field |
|---:|---:|---|
| 0 | 4 | Magic `KASF` (`0x4653414b` as little-endian uint32) |
| 4 | 4 | Version, currently `1` |
| 8 | 8 | Channel count, uint64 |
| 16 | 8 | Frame count, uint64 |
| 24 | 8 | Frame duration in seconds, float64 |

**The KASF v1 header does not contain the sample rate.** The adapter must receive the actual KASF Reader sample rate through trusted side metadata or the original processing configuration. It must not infer the rate from frame duration or the source filename.

### Frame/channel body

For each frame, then each channel, the body stores:

1. uint64 little-endian component count;
2. that many 6-byte components.

The Rev.0.9.20 source's `KASF_CHUNKS.connectPhases()` reads each 6-byte component as:

- frequency: unsigned 24-bit little-endian, mapped by `qf / 0xFFFFFF * 96000` Hz;
- amplitude: unsigned 14-bit value, mapped by `qa / 0x3FFF`;
- phase: unsigned 10-bit value assembled from the upper two bits of byte 4 and all eight bits of byte 5, mapped by `qp * 2π / 1024`.

A decoder must reject truncated counts, unsafe component counts, incomplete component payloads, unsupported versions, invalid frame/channel geometry, and unexpected trailing bytes.

## 3. Reader v1.2 behavior visible in the source

The source exposes `KASF05_Reader.parameters()` and `KASF05_Reader.render()` for the optimizer's local synthesis path.

`parameters(rate, frameDuration)` uses:

```text
N = max(1, round(rate * frameDuration))
H = max(1, round(rate * frameDuration / 2))
```

The local Reader path:

- re-quantizes each component using the KASF v1 24/14/10-bit ranges;
- uses a periodic Hann window `0.5 - 0.5*cos(2πn/N)`;
- synthesizes `amplitude * sin(2π * frequency * n / rate + phase)`;
- uses frame-relative sample index `n` and overlap-adds frames at `m * H`;
- returns floating-point samples before full-file global peak normalization.

The Rev.0.9.20 source explicitly labels its diagnostic synthesis as occurring before full-file global peak normalization. The local `KASF05_Reader.render()` function is therefore **not by itself proof of the final normalized PCM output**. Its optional approximate oscillator path is intended only for short candidate scoring; it must never be used for KRM Base capture.

The source also contains post-Worker phase-connection logic. `KASF_CHUNKS.connectPhases()` can adjust stored 10-bit phases at chunk seams. Consequently, a Base must be rendered from the final merged `.kasf` file, after Worker results have been trimmed, channel-merged, seam-connected, and serialized.

## 4. Source PCM domain must match the KASF input pipeline

The Rev.0.9.20 KASF pipeline may convert the input to a configured target sample rate. Its WAV streaming path can use either a 49-tap resampling table or linear interpolation, depending on the selected processing mode. The KASF output header records frame duration but not the target sample rate or resampling mode.

Therefore, `X` cannot automatically be assumed to mean the original WAV's decoded samples. `X` must be defined as the exact canonical PCM presented to the KASF representation pipeline, after the selected decoding, channel ordering, resampling, and boundary policy. If the KASF processing configuration changes any of these, the KRM Source stream must follow the same transform.

The KRM prototype currently accepts **signed integer PCM** only. The KASF internal analysis/Reader code uses floating-point buffers and does not, in the audited source, define a complete public float-to-integer PCM export quantizer for this KRM use. Before production capture, the adapter contract must fix:

- the PCM bit depth and signedness;
- float-to-integer scale, rounding rule, clipping rule, and NaN/Infinity handling;
- the exact global normalization algorithm and where it is applied;
- whether `X` is quantized before or after any global gain operation;
- the exact final Reader sample count and channel mapping.

No default quantizer or normalization constant is invented by this draft.

## 5. Required adapter interface

A concrete adapter must supply the following metadata before streaming samples:

```text
format_version
engine_revision
reader_version
sample_rate_hz
channels
channel_order
sample_count_per_channel
sample_width_bytes
source_domain_id
resampler_profile (or identity)
normalization_profile
pcm_quantization_profile
phase_join_complete = true
final_kasf_sha256
```

It must then provide two synchronized iterators:

- `source_pcm_chunks`: canonical Source PCM, channel-planar integer values;
- `canonical_reader_pcm_chunks`: final Reader Base PCM after all quantization, full-file normalization, and output PCM conversion.

Both iterators must:

- start at sample zero;
- use identical chunk boundaries;
- emit the declared number of channels and samples;
- use identical sample rate, sample width, channel order, and timeline;
- have no gaps, duplicate samples, implicit resampling, or implicit channel conversion.

KRC validates shape and arithmetic, but cannot prove the provenance of a PCM iterator merely because the caller labels it as KASF. The final KASF hash and Reader metadata are provenance records, not cryptographic proof that a particular program produced the PCM.

## 6. Reader streaming parity gate

Before using a streaming Reader to generate KRM Base, compare it with the canonical full Reader over the same final `.kasf` file.

Required gate:

1. Render the entire final file with the canonical Reader.
2. Render the same file with the proposed streaming/segmented Reader using multiple chunk sizes, including boundaries that do not align to `H`.
3. Apply the same global normalization and PCM quantization to both paths.
4. Compare every integer PCM sample and channel.
5. Require exact equality, not an RMS or perceptual tolerance, before calling the path canonical.
6. Repeat for mono, stereo, and supported multichannel cases; short files; odd `N`; phase-joined chunk seams; silence; full-scale peaks; and last-frame truncation.

If exact equality is not achieved, the streaming path is a diagnostic or approximate path only and must not be used for authoritative KRM Base capture.

## 7. Current implementation status

| Item | Status |
|---|---|
| KASF v1 header/body layout audit | Source-inspected in Rev.0.9.20 |
| Reader v1.2 local OLA formula audit | Source-inspected |
| Post-Worker phase seam handling audit | Source-inspected |
| External sample-rate and preprocessing metadata | Required, not embedded in KASF v1 header |
| Canonical full-file normalization + PCM quantization profile | Not established by the audited local Reader function |
| Standalone KASF file decoder/Reader adapter for KRM | Not implemented |
| Full-vs-streaming sample-exact parity test | Not implemented |

Until the remaining items are established, the KRM prototype must continue to accept externally supplied Base PCM and must not claim direct KASF Reader integration.
