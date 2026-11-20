# KRC — KRM Residual Capture Draft 0.2

Status: interface/algorithm draft plus Python WAV and synchronized-chunk implementations.

## 1. Purpose

KRC captures the final global residual after KASF has completed its own Generator, KASE, MRA, KASF v1 serialization, and selected Reader path. KRC's Raw Residual is not the short local residual patch used internally by MRA.

## 2. Input contract

- `SourcePCM`: canonical source integer PCM.
- `BasePCM`: final canonical KASF Reader output, already mapped to the same time/sample/channel domain.
- `Timeline`: exact sample rate, sample count, channel count/order, bit depth, and alignment behavior.

The adapter must not use browser playback gain, speaker output, an analytical approximation, or a pre-quantized Generator buffer as Base.

## 3. Core operation

For each sample and channel, in a wider signed integer domain:

```python
residual = source_pcm - base_pcm
restored = base_pcm + residual
assert restored == source_pcm
```

The assertion is required across every sample/channel. The prototype stores Base and Residual as signed int64; 32-bit PCM differences fit this range.

## 4. Implemented interfaces

### WAV convenience API

`capture_residual(source_wav, base_wav, output_krmi, chunk_samples=65536)`

- accepts uncompressed integer PCM WAV supported by Python's `wave` module;
- requires identical channels, sample rate, sample width, and frame count;
- decodes and processes bounded blocks;
- rejects an output path that would overwrite Source or Base.

### Direct synchronized-chunk API

`capture_residual_chunks(source_chunks, base_chunks, spec, output_krmi, chunk_samples=65536, base_provenance=None)`

- accepts channel-planar integer PCM chunks directly;
- does not require a temporary WAV export;
- requires matching Source/Base block boundaries;
- requires all blocks except the final one to have exactly `chunk_samples` samples per channel;
- validates integer types, channel count, sample count, and PCM range;
- accepts optional JSON-compatible `base_provenance` metadata (engine, revision, Reader version, normalization, and alignment details);
- is the intended seam for a future KASF Reader adapter and can process recordings beyond the classic RIFF/WAV size ceiling, provided the caller supplies streaming PCM chunks.

## 5. Alignment rule

Source and Base must already be in a common PCM domain. Draft 0.2 does not resample, remap channels, or infer offsets. A future KASF Adapter must explicitly define its projection from Reader output into the Source PCM timeline.

If KASF runs at a different sample rate, it must return a deterministically aligned Base stream and record the exact projection parameters. The residual then preserves any difference introduced by the projection, but the projection must remain reproducible and correctly aligned.

## 6. Integrity and failure handling

- CRC-32C is calculated per Base and Residual payload.
- SHA-256 is calculated over canonical Source/Base PCM bytes and over both complete int64 payload streams.
- Each output is written to a unique temporary file.
- The final path is replaced only after all blocks, digests, and manifest fields are complete.
- Any Python exception removes the temporary file.

There is no crash-resume journal in Draft 0.2.

## 7. Restoration

- `restore_krmi()` reconstructs classic PCM WAV where RIFF size limits permit.
- `restore_raw_pcm()` writes frame-interleaved little-endian PCM without a RIFF/WAV header and is the route for very large outputs.
- Raw output format metadata is returned by the CLI and remains available in the KRM-IF manifest.

## 8. Future KASF Adapter requirements

1. Obtain the final saved KASF v1 representation.
2. Run the intended Reader version and full canonical normalization/OLA path.
3. Preserve the Reader's state across chunks; do not reset overlap-add or global normalization at arbitrary boundaries.
4. Prove streaming Reader output matches canonical full Reader output sample-for-sample.
5. Align channels/timebase explicitly and deliver integer PCM chunks.
6. Keep KASF's current file format and Reader compatibility unchanged.

## 9. Explicit non-equivalence

MRA's local patches are an optimization work buffer. Its sampled validation metrics are not a whole-file residual. KRC's Raw Residual is the final global difference between the entire canonical Source and final canonical Reader output.
