# KRM-IF Container Draft 0.2 — Prototype Binary Layout

Status: prototype format implemented by the Python package. Not a frozen production standard.

## 1. Compatibility

- New writers emit header version `0.2` and manifest revision `prototype-0.2`.
- The reader accepts the Draft 0.1 layout (`0.1` / `prototype-0.1`) because the physical block layout did not change.
- No reader for future major versions is implied.

## 2. Numeric and byte-order policy

- Container integers: little-endian.
- Base and Residual payloads: signed int64 little-endian, channel-planar within each block.
- Compression: none.
- Original Source PCM frame bytes are not duplicated in the container; their SHA-256 is recorded.
- Source PCM 8-bit WAV uses unsigned storage on disk and signed centered integers in memory.

## 3. File header

Python struct format: `<8sHHI` (16 bytes).

| Field | Type | Meaning |
|---|---|---|
| magic | 8 bytes | `KRMIF\r\n\x1a` |
| major | uint16 | 0 |
| minor | uint16 | 2 for new files; 1 accepted for legacy files |
| manifest_length | uint32 | UTF-8 JSON byte length |

The UTF-8 JSON manifest follows immediately. Maximum manifest size is 16 MiB. JSON is sorted by key, compactly serialized, and rejects non-finite numbers when written.

## 4. Manifest constraints

The reader validates required section types and the following limits before block reads:

- channels: 1–32
- sample rate: 1–768,000 Hz
- sample count: 0 through signed-64 maximum
- sample width: 1, 2, 3, or 4 bytes
- chunk samples per channel: 1–131,072
- block count: exactly `ceil(sample_count / chunk_samples)` and representable by uint32 block indices
- payload encoding: `signed_int64_little_endian_channel_planar`
- compression: `none`

The expected total file size is computed from the declared manifest and compared with the actual file size before any block payload allocation.

## 5. Block header

Python struct format: `<4sIQIHHIIII` (40 bytes).

| Field | Type | Meaning |
|---|---|---|
| marker | 4 bytes | `BLK1` |
| block_index | uint32 | Zero-based contiguous block index |
| start_sample | uint64 | First sample index in block |
| sample_count | uint32 | Samples per channel in block |
| channels | uint16 | Channel count |
| flags | uint16 | Must be zero |
| base_length | uint32 | Base payload bytes |
| residual_length | uint32 | Residual payload bytes |
| base_crc32c | uint32 | CRC-32C of Base payload |
| residual_crc32c | uint32 | CRC-32C of Residual payload |

Base payload follows the block header, then Residual payload. Each payload length must equal `channels * sample_count * 8`. Every block must have exactly the expected number of samples; partial middle blocks are rejected.

## 6. Integrity

- Per-payload integrity: CRC-32C (Castagnoli).
- Whole-source PCM digest: SHA-256 of canonical interleaved source PCM bytes.
- Whole-Base PCM digest: SHA-256 of canonical interleaved Base PCM bytes.
- Whole-Base-payload digest: SHA-256 of concatenated channel-planar int64 Base payloads.
- Whole-Residual-payload digest: SHA-256 of concatenated channel-planar int64 Residual payloads.
- Optional Base provenance: JSON-compatible producer/Reader/alignment metadata; this is descriptive and does not prove the Base came from that Reader.

The v0.1 reader path requires the two PCM digests; payload-wide digests are optional for legacy files and required for v0.2 files. BLAKE3 is not implemented in this package.

## 7. Writer behavior

1. Create a unique temporary file in the destination directory.
2. Write the header and manifest with fixed-width digest placeholders.
3. Stream Base and Residual blocks once, updating PCM and payload digests.
4. Patch only the small manifest, requiring exactly the same serialized length.
5. Flush and fsync the file.
6. Atomically replace the destination and best-effort fsync the parent directory.

The writer no longer copies the complete block body into a second temporary file. A failed operation removes its temporary file and leaves an existing destination untouched.

This is atomic file completion, not a crash-resumable journal. A hard process termination may leave an uncommitted uniquely named `.partial` file.

## 8. Chunking and memory

Default: 65,536 samples per channel. Maximum prototype block: 131,072 samples per channel. Base and Residual each use int64. At the maximum of 32 channels, a single Base or Residual payload can be approximately 32 MiB; both are read per block. The prototype is bounded by block size, but it is not a low-memory native implementation.

## 9. Deliberate omissions

No compression, no floating-point PCM, no resampling, no channel projection, no KASF Reader invocation, no KASF reference block writer, no analysis/event block writer, no crash-resume journal, and no atomic KASF/KRM cross-engine manifest. The current `.krmi` file proves the paired Base/Residual invariant only.
