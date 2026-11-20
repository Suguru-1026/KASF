# KRM-IF Metadata Contract — Draft 0.5

Status: logical contract update for the experimental FastGen bridge. The physical KRM-IF container remains prototype v0.2.

## 1. Key distinction

The prototype bridge Base is produced by the local KASF05_Reader OLA equation plus an explicit KRM quantizer. It is not labelled as the canonical full-application KASF PCM export. Manifest provenance must preserve this limitation.

## 2. Base provenance fields

The prototype records the following under `base_provenance` where available:

- `origin`: experimental FastGen + local Reader OLA
- `engine`, `engine_revision`
- `reader_version`: source version and local OLA profile
- `renderer`: native C++ OLA implementation name
- `source_wav_sha256`, `kasf_sha256`, `base_wav_sha256`
- `sample_rate_hz`, `sample_count`
- `normalization_policy`: `none`
- `integer_pcm_quantizer`: `KRM-PROTO-PCM-Q-v1`
- `alignment`: identity after symmetric guard crop, with same sample rate/channel order/count
- `edge_padding_samples_each_side`
- `canonical_kasf_export`: `false`

Hashes identify the supplied files. They do not by themselves prove which software generated them or that the KASF web application was executed.

## 3. PCM quantizer profile

For Reader float `x`, bit depth `b`, signed scale `S=2^(b-1)`:

```text
q = floor(x*S + 0.5)
q = clamp(q, -S, S-1)
```

Non-finite values map to zero; no normalization or dither is applied. This mirrors `Math.round()` for ordinary finite values but is a KRM prototype choice, not official KASF export behavior.

## 4. Source domain

FastGen currently accepts the WAV's decoded samples at its original sample rate and channel order; it performs no resampling or channel remapping. The resulting `X` is the integer PCM frame stream in the input WAV. This differs from any KASF application path that might resample or otherwise prepare the Source before analysis.

## 5. Integrity and reconstruction

The raw integer residual remains authoritative:

```text
R = X - B
X = B + R
```

Physical prototype v0.2 stores paired int64 Base and Residual payloads, block CRC-32C, and whole-payload SHA-256 digests. Analysis and candidate metadata cannot alter exact restoration.
