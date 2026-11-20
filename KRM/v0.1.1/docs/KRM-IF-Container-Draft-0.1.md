# KRM-IF Container Draft 0.1 — Prototype Binary Layout

Status: prototype format used by the supplied Python code. Not a frozen production standard.

## 1. Byte order and numeric policy

- All container integers: little-endian.
- Base/Residual payloads: signed int64 little-endian.
- Payload layout: channel-planar; each channel's samples are contiguous within the block.
- Compression: none.
- Source PCM WAV bytes are not copied into the container; only their SHA-256 is recorded.

## 2. File header

Python struct format: `<8sHHI` (16 bytes).

| Field | Type | Meaning |
|---|---|---|
| magic | 8 bytes | `KRMIF\r\n\x1a` |
| major | uint16 | 0 |
| minor | uint16 | 1 |
| manifest_length | uint32 | UTF-8 JSON byte length |

The JSON manifest follows immediately. The reader currently limits it to 16 MiB.

## 3. Manifest fields

The current manifest includes:

- `format`, `container_revision`, `created_by`, `purpose`
- `audio.channels`, `sample_rate_hz`, `sample_count`, `sample_width_bytes`, `sample_format`, `channel_layout`, `timebase`
- `container.chunk_samples_per_channel`, `block_count`, `payload_encoding`, `compression`, `block_integrity`
- `reconstruction.source_pcm_sha256`, `base_pcm_sha256`, equation and overflow policy
- `limitations`

Manifest JSON is UTF-8, sorted by key, with compact separators.

## 4. Block header

Python struct format: `<4sIQIHHIIII` (40 bytes).

| Field | Type | Meaning |
|---|---|---|
| marker | 4 bytes | `BLK1` |
| block_index | uint32 | Zero-based, contiguous block index |
| start_sample | uint64 | First sample index in this block |
| sample_count | uint32 | Samples per channel in this block |
| channels | uint16 | Channel count |
| flags | uint16 | Must be zero in prototype 0.1 |
| base_length | uint32 | Base payload byte count |
| residual_length | uint32 | Residual payload byte count |
| base_crc32c | uint32 | CRC-32C of Base payload |
| residual_crc32c | uint32 | CRC-32C of Residual payload |

The Base payload immediately follows the header, then the Residual payload.
Each payload length must equal `channels * sample_count * 8`.

## 5. CRC and whole-signal digests

- Per-payload integrity: CRC-32C (Castagnoli polynomial `0x1EDC6F41`, reflected implementation polynomial `0x82F63B78`).
- Source/Base whole PCM digest: SHA-256 of the original interleaved PCM frame bytes read from the WAV files.
- BLAKE3 is not implemented in this prototype. It can be evaluated for a future production revision, but must not be claimed for this implementation.

## 6. Chunking

Default: 65,536 samples per channel. The final block may be shorter. Blocks are contiguous and cover `[0, sample_count)` exactly with no gaps or overlap.

The writer creates a `.partial` file, flushes and fsyncs it, then replaces the destination after completion. This reduces exposure to partially written final files but is not a resumable journal. If the process stops before the final rename, the `.partial` file may remain and is not considered committed.

## 7. PCM interpretation

Source WAV sample widths supported by the prototype:

- 8-bit: unsigned bytes on disk, converted to signed `[-128,127]` internal integer values.
- 16-bit: signed little-endian.
- 24-bit: signed little-endian with sign extension.
- 32-bit: signed little-endian.

Base samples are interpreted in the same PCM domain. Residuals are signed int64 differences. Restored samples must fit the declared Source PCM range; otherwise restore/verify fails.

## 8. Deliberate omissions

No compression, no floating-point PCM, no resampling, no channel map, no KASF references, no analysis block writer, no candidate block writer, no crash-resume journal, no cross-revision transaction records. The format is a working proof-of-concept for paired Base/Residual chunks only.
