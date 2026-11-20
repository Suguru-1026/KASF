# KASF Reader Adapter Contract — Draft 0.5

Status: local Reader equation has been implemented twice (Python reference and C++ bridge) and compared against the actual Rev.0.9.20 JavaScript `KASF05_Reader.render()` implementation. This is still **not** a canonical full-application Reader/export contract.

## 1. Confirmed KASF v1 binary layout

The actual Rev.0.9.20 `buildKASF()` writes `KASF` as the four-byte magic. Header: `KASF`, uint32 version 1, uint64 channels, uint64 frame count, float64 frame duration seconds. This is 32 bytes, little-endian. The KASF v1 body stores each frame/channel as uint64 component count followed by six bytes per component.

Draft 0.4 mistakenly checked for `KFSA`; this was a prototype decoder/test fixture error. Draft 0.5 corrected the parser, tests, and writer. The transposed magic is rejected.

## 2. Packed component decoding

- frequency: qf uint24 little-endian; `f = qf * 96000 / 0xFFFFFF`
- amplitude: qa uint14; `a = qa / 0x3FFF`
- phase: qp uint10; `phase = qp * 2π / 1024`

## 3. Reader geometry and synthesis

For sample rate `rate` and frame duration `duration`:

```text
N = max(1, Math.round(rate * duration))
H = max(1, Math.round(rate * duration / 2))
```

Compute N and H independently. At 44.1 kHz and 5 ms, N=221 and H=110.

For each frame m, each channel and local sample n:

```text
sum[n] = Σ (a * sin(2π * f * n / rate + phase))
window[n] = 0.5 - 0.5 * cos(2π * n / N)
output[m*H+n] += window[n] * sum[n]
```

Clip the emitted timeline to the externally supplied sample count. The KASF header does not store source rate or sample count. Components in the final saved KASF representation are already quantized; do not repeat phase seam correction in the Reader.

## 4. Implementations and test results

- `krm_proto.kasf_reader`: bounded-memory Python float64 reference OLA renderer.
- C++ FastGen `--base-wav`: native OLA over its own quantized output frames, followed by KRM-PROTO-PCM-Q-v1 conversion.
- Node harness: extracts and executes the actual `KASF05_Reader` implementation from the user's Rev.0.9.20 HTML to compare float64 output.

10-second synthetic test, 48 kHz, stereo, 480,480-sample guarded timeline:

- compared values: 960,960 float64 values;
- max absolute JS-vs-Python difference: 2.220446049250313e-16;
- mean absolute difference: 2.5901627633556662e-18;
- JS and Python binary float arrays are not bit-identical due to Math.sin / libm rounding;
- C++ and Python quantized Base WAVs were byte-identical on this 16-bit test and separate 8/16/24/32-bit cases.

This is strong evidence for matching the **local OLA equation**, not proof of an app-level final render path.

## 5. Experimental integer quantizer

`KRM-PROTO-PCM-Q-v1`:

- scale signed PCM by `2^(bits-1)`;
- round with `floor(x + 0.5)` after scaling, matching JavaScript `Math.round()` for the finite values expected here;
- saturate to the signed integer range;
- map non-finite values to zero;
- apply no normalization.

This quantizer is a KRM experiment, not a specification discovered in KASF Rev.0.9.20.

## 6. What remains unresolved

1. Exact Source PCM domain after KASF's input decoder, channel handling and optional resampling.
2. Full application-level frame merge/phase-join and Reader execution parity for all production routes and Worker configurations.
3. Whether any application-wide gain or normalization is applied after local `KASF05_Reader.render()` in a user-visible export path.
4. The official final float-to-integer export quantizer, clipping, dither and non-finite policy.

Until those are proven, this bridge must record `canonical_kasf_export: false`. KRC's exactness claim is restricted to its recorded Source/Base integer pair.
