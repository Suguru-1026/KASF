# KRM Prototype Architecture Draft 0.3

Status: implementation map for the Python research package. The KRM-IF file container remains revision `prototype-0.2`; package version is `0.3.0`.

## 1. Scope

Draft 0.3 advances two boundaries:

1. KRC captures exact integer-PCM residuals with durable block checkpoints and verified resume.
2. The KASF Reader adapter contract is based on an audit of the actual Rev.0.9.20 source rather than assuming that a local synthesis function is the complete final Reader.

No KASF source file is modified and no KASF integration is claimed.

## 2. Module map

| Module | Responsibility |
|---|---|
| `pcm.py` | PCM/WAV metadata, integer decode/encode, int64 planar payload conversion |
| `capture.py` | KRC WAV adapter and synchronized PCM chunk API |
| `resumable.py` | append-only checkpointed KRC writer, journal validation, prefix replay, resume |
| `container.py` | KRM-IF v0.2 manifest, block writer/reader, CRC-32C, SHA-256, structural validation |
| `restore.py` | exact PCM reconstruction, digest verification, WAV/raw output |
| `events.py` | bounded-memory frame extraction, P² median estimate, coarse event grouping |
| `predictor.py` | reversible integer prediction and streaming verification |
| `candidates.py` | KRM-FC metadata and per-frame/per-channel proposal validation |
| `__main__.py` | command-line interface, including explicit `--resume` |

## 3. KRC checkpoint boundary

Every capture uses `<output>.partial` and `<output>.journal.json`. A complete data block is fsynced before the journal is advanced. Resume truncates uncommitted tails, replays the Source/Base prefix, and verifies the stored Base and Residual before continuing. Finalization is journaled before manifest patch and atomic rename.

Resume requires fresh, replayable input iterators from sample zero. It does not trust a saved block counter alone.

## 4. KASF Reader adapter findings

Rev.0.9.20 source inspection verified the KASF v1 32-byte header, frame/channel count-prefixed body, 24/14/10-bit component interpretation, the local quantized periodic-Hann/sine OLA Reader path, and post-Worker phase-connection stage.

Two critical details prevent prematurely writing a production adapter:

- the v1 header does not include sample rate;
- the local Reader function is explicitly pre-global-normalization and does not alone establish the final integer PCM quantizer.

The adapter must use the final merged KASF file, carry side metadata for sample rate and source preprocessing, and prove full-reader versus streaming-reader integer PCM equality after the same normalization and PCM quantization. See `KASF-Reader-Adapter-Contract-Draft-0.3.md`.

## 5. KRM-IF and exact restoration

The `.krmi` structure remains the Draft 0.2 paired Base/Residual layout. `R = X - B` is stored as signed int64, while Base stays inside the declared PCM range. Reconstruction remains `X = B + R` with no reanalysis. KRM-IF v0.2 digest semantics and Draft 0.1 read compatibility are unchanged.

## 6. Integrity and recovery

- Structural checks and block CRC-32C are performed before accepting payload blocks.
- Whole Source/Base PCM and Base/Residual payload SHA-256 digests are retained.
- The sidecar journal is protected by SHA-256 over canonical JSON.
- The writer commits data before journal metadata and replays committed Source/Base chunks on resume.
- The journal is not yet a KRM-IF block and does not coordinate KASF candidate commits.

## 7. Remaining integration work

1. Obtain/define the complete standalone KASF Reader v1.2 output path, including full-file global normalization and PCM quantizer.
2. Define canonical Source PCM after KASF's decode/resampling/channel pipeline.
3. Implement a Reader-to-chunk adapter only after the exact parity gate passes.
4. Implement KKI transport and KASF/KRM atomic candidate transactions.
5. Add full analysis/event algorithms and serialized analysis blocks.
6. Evaluate KRM-SIM as a predictor, without making it a dependency of exact restoration.
7. Freeze a production KRM-IF format only after interoperability and long-duration testing.

## 8. Explicit non-claims

The tests do not prove the Reader adapter, sample-exact full-file normalization, 26-hour processing, Chromebook performance, concurrent capture, or production power-loss behavior. The user-supplied KASF processing-time estimate remains unverified by this package.
