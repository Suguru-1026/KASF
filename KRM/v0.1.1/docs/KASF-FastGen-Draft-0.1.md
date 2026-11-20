# KASF FastGen — Draft 0.1

Status: independent C++17 baseline encoder, writing KASF v1 containers. It is not a port of the complete Rev.0.9.20 Generator/KASE/MRA stack.

## 1. Input and output contract

- Input: RIFF/WAVE, uncompressed integer PCM 8/16/24/32.
- Supported: 1–8 channels; 1,000–768,000 Hz.
- KASF output: v1, 32-byte little-endian header, `KASF` magic, channel count, frame count, frame duration; count-prefixed 6-byte components.
- v1 component fields: frequency uint24, amplitude uint14, phase uint10.
- Sample rate and sample count are preserved in the sidecar, not in the KASF v1 header.

## 2. Analysis

Each channel/frame is independently analyzed using periodic Hann weighting, radix-2 FFT, positive-frequency peak selection, log-magnitude parabolic interpolation, weighted sine/cosine least-squares fitting, and iterative subtraction of the quantized component. Frequency bins below `min_hz`, at/above Nyquist, or above the KASF 96 kHz frequency field are excluded from peak selection.

Default parameters: frame duration 10 ms, at most 48 components/channel/frame, amplitude stop threshold -58 dBFS, minimum frequency 15 Hz. Frame duration is constrained to 1–100 ms; max components to 1–4096.

The engine writes quantized components before subtracting them from the frame residual, keeping the pursuit loop aligned with the values that the Reader will actually synthesize.

## 3. Reader-compatible Base emission

The optional `--base-wav` output accumulates quantized component sinusoids through periodic-Hann overlap-add, with N and H independently rounded according to the audited local Reader formulas. It does not normalize. It uses KRM-PROTO-PCM-Q-v1 for integer WAV output and is not an official KASF export.

C++ and Python implementations were compared after PCM quantization on 8/16/24/32-bit synthetic WAVs; each Base PCM comparison was byte-identical. A 10-second 48 kHz stereo test also matched the actual Rev.0.9.20 JavaScript `KASF05_Reader.render()` float output within 2.22e-16 maximum absolute difference.

## 4. Boundary guard

When enabled, the Source timeline is padded by one hop on each side. The initial guard is seeded from the first complete Source window with its component phases shifted backward by H/rate. The tail is seeded from the last complete Source window and phase-shifted forward per guard frame. This is a heuristic extension for improved edge coverage, not a universal transient predictor.

## 5. Deliberate exclusions

No resampling, channel remapping, temporal component tracking, Worker phase-seam correction, STN/HPSS/Matrix Pencil/NOMP/GVP/ADMM/DPSS/SST/Haar-WPT-MP/KASE optimization. The algorithm is a baseline extraction model suitable for KRM pipeline and residual research.
