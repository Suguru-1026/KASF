# KASF Reader Adapter Contract — Draft 0.4

Status: source-audited contract plus a diagnostic Python decoder/OLA renderer. This is **not** canonical KASF-to-KRM integration.

## Audit correction carried from Draft 0.3

Draft 0.3 wording could be read as if Rev.0.9.20 had a final Reader PCM export followed by a global peak normalization stage. That is not established by the source. The `KASF05_Reader.render()` comment says it reproduces the old local synthesis *before* full-file global peak normalization, but the audited HTML does not expose a complete public full-file Reader-to-PCM export pipeline. `findGlobalPeak(channels)` is used on the source-side analysis path (for logging/threshold context); it is not evidence of a final Reader-output normalization operation. Therefore KRM must **not** apply or assume a global peak normalization multiplier.

## Verified KASF v1 layout and synthesis

- 32-byte little-endian header: `KASF`, uint32 version=1, uint64 channels, uint64 frame count, float64 frame duration seconds.
- No sample rate or original/resampled sample count in the header. These must be supplied by a trusted sidecar/configuration.
- Each frame/channel: uint64 component count, then 6-byte packed components.
- qf: uint24 LE, frequency = `qf * 96000 / 0xFFFFFF` Hz.
- qa: 14 bits from byte 3 and low 6 bits of byte 4, amplitude = `qa / 0x3FFF`.
- qp: low 2 bits of byte 4 and byte 5, phase = `qp * 2π / 1024`.
- Reader geometry: `N=max(1, round(rate*frameDuration))`; `H=max(1, round(rate*frameDuration/2))`. Do not replace H with `round(N/2)`; at 44.1 kHz / 5 ms, N=221 and H=110.
- Per frame, sample-local component sum is `Σ a*sin(2πfn/rate + phase)`, multiplied by periodic Hann `0.5 - 0.5*cos(2πn/N)`, then overlap-added at frame start `m*H`.
- Components are already quantized by the saved v1 representation; phase seam connection has already modified bytes in the final merged file and must not be repeated by the reader.

## Resampling and timeline domain

KASF input preparation can use the 49-tap windowed-sinc resampler when coherent FFT mode is enabled, or linear interpolation when disabled. KASF v1 does not store the selected resampler profile. KRM Source `X` must be the actual PCM entering the component analysis after the same decode/channel order/resampling boundary rules—not automatically the original WAV samples.

`sample_count` must be provided externally. KASF frame count is planned from the target-rate sample count and Reader hop/size. The final frame can extend past the declared sample timeline; the Reader renderer must clip output to the sidecar sample count. It must reject a timeline that is not covered by the frame set.

## New diagnostic implementation in Draft 0.4

`krm_proto.kasf_reader` provides:

- strict KASF v1 header/body parsing;
- exact 24/14/10-bit field decoding;
- Reader N/H geometry using the source formula;
- bounded-memory streaming OLA rendering to channel-planar float64 chunks;
- no hidden normalization, clipping, integer conversion, or phase re-joining.

The renderer mirrors the audited local `KASF05_Reader.render()` equation and accumulation order. It is a research/diagnostic path. It does not prove equality with a missing standalone full-file Reader export, and Python/JS transcendental functions may differ by floating-point rounding. Its output is float64, not KRM's signed-integer PCM.

## Still required before authoritative KRC capture

1. Establish a single canonical Reader implementation and exact output timeline.
2. Establish the KASF source PCM export after decode/resampling, with its exact sample values.
3. Decide and version a PCM quantizer (scale, rounding, clipping, non-finite policy) shared by Source and Base.
4. Define whether any post-render gain/normalization exists; absent a specified operation, apply none.
5. Compare the diagnostic renderer against the canonical Reader across mono/stereo/multichannel, odd N, multiple frame durations, chunk sizes, phase-connected seams, silence, and truncated final frames.
6. Only after parity passes, feed synchronized integer Source/Base chunks into KRC.

Until then, diagnostic float64 output must not be labelled canonical Base PCM or used to claim exact KASF reconstruction.
