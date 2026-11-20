# KRM-IF Metadata Contract — Draft 0.4

Status: metadata contract draft. The physical KRM-IF container remains prototype-0.2; this document does not change its bytes or claim a frozen production format.

## 1. Design rule

Metadata must describe the exact sample domain of the paired `BASE` and `RAW_RESIDUAL` payloads. It must not silently transform audio. Exact restoration depends only on integer payloads and their integrity fields; analysis and provenance may be discarded without changing reconstruction.

## 2. Required logical metadata groups

### Identity

- `format`: `KRM-IF`
- `schema_revision`: explicit metadata schema revision, independent of physical container revision
- `capture_id`: unique capture UUID
- `created_utc`: RFC 3339 UTC timestamp
- `producer`: KRM implementation name/version

### Audio domain

- `sample_format`: signed integer PCM
- `sample_width_bytes`: 1–4
- `sample_rate_hz`: positive integer
- `channels`: positive integer
- `channel_order`: explicit ordered labels; never infer a speaker layout from channel count
- `sample_count`: samples per channel
- `timeline_origin`: integer sample index, normally zero
- `domain_id`: stable identifier shared by Source, Base and Residual

### Source transform

- `decoder_profile`: codec/container decoder and version
- `source_sample_rate_hz`: original decoded rate
- `resampler_profile`: `identity`, `KASF-49tap-windowed-sinc`, `KASF-linear`, or a separately versioned profile
- `resampler_parameters`: phase count, tap count, cutoff/window, boundary extension, output-length rounding
- `channel_mapping`: explicit input-to-domain mapping
- `source_pcm_sha256`: hash of canonical integer Source bytes in the declared interleaving/endianness convention

### Base provenance

- `base_engine`: KASF engine revision
- `base_format`: KASF format version
- `reader_profile`: exact implementation and revision, not merely a label such as `Reader v1.2`
- `kasf_file_sha256`: digest of the final merged KASF file after phase seam connection
- `reader_sample_rate_hz`: explicit because KASF v1 header omits it
- `reader_frame_count`, `reader_frame_duration_s`
- `reader_N`, `reader_H`
- `reader_output_sample_count`
- `reader_normalization`: explicit operation/profile or `none`
- `pcm_quantization_profile`: versioned mapping from Reader float output to signed integer PCM
- `base_pcm_sha256`: hash of canonical integer Base bytes

### Reconstruction and integrity

- `residual_definition`: `SOURCE_MINUS_BASE`
- `residual_integer_width`: signed int64 in the prototype
- `source_pcm_sha256`, `base_pcm_sha256`
- `base_payload_sha256`, `residual_payload_sha256`
- per-block CRC-32C and exact block coverage

### Optional analysis

- algorithm identifiers and implementation revisions
- analysis parameters, window/hop, thresholds and calibration
- event/candidate identifiers, sample intervals, confidence and uncertainty
- parent Source/Base/Residual revision identifiers

Optional analysis must never overwrite the exact residual or imply that a detected event is a semantic source label.

## 3. Required consistency checks

1. Source and Base have identical `domain_id`, sample rate, channel order, sample count and integer format.
2. `R[n,c] = X[n,c] - B[n,c]` is computed in signed int64 with overflow checks.
3. The declared source and base hashes match the canonical PCM bytes used for capture.
4. The final KASF digest and Reader provenance are recorded, but are not treated as cryptographic proof of execution.
5. Any resampling, channel mapping, gain, normalization or quantization operation must be explicitly named and versioned; unknown means reject authoritative capture.
6. Missing metadata may be accepted only in diagnostic mode, never silently promoted to canonical capture.

## 4. Status

Draft 0.4 defines logical metadata semantics only. The current prototype's manifest has not yet been migrated to these fields. A later container revision should add a validated `source_domain` and `reader_provenance` section while retaining backward reading of prototype-0.1/0.2 files.
