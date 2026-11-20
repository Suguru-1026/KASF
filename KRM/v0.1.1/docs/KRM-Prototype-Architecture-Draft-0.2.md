# KRM Prototype Architecture Draft 0.2

Status: implementation map for the Python research package. It does not replace the higher-level KRM Integrated Design Draft 1.0.

## 1. Scope

Draft 0.2 is intended to harden the safest, measurable core before implementing sophisticated residual analysis:

1. obtain already-aligned Source and Base PCM;
2. compute Raw Residual exactly;
3. store paired Base/Residual blocks with integrity checks;
4. reconstruct exact PCM without rerunning analysis;
5. inspect residual activity in bounded memory;
6. experiment with integer prediction and frame-level candidate metadata.

The package deliberately does not execute KASF Generator, KASE-2.1, MRA, or Reader.

## 2. Module map

| Module | Responsibility |
|---|---|
| `pcm.py` | PCM/WAV metadata, integer decode/encode, int64 planar payload conversion |
| `capture.py` | KRC WAV adapter and synchronized PCM chunk API |
| `container.py` | KRM-IF v0.2 manifest, block writer/reader, validation, CRC-32C, atomic paths |
| `restore.py` | exact PCM reconstruction, digest verification, WAV/raw output |
| `events.py` | bounded-memory frame extraction, P² median estimate, coarse event grouping |
| `predictor.py` | reversible integer prediction and streaming verification |
| `candidates.py` | KRM-FC metadata and per-frame/per-channel proposal validation |
| `__main__.py` | command-line interface |

## 3. KRC API boundary

`capture_residual()` is a convenience wrapper for small/ordinary PCM WAV files.

`capture_residual_chunks()` is the intended future KASF adapter boundary. It receives already-aligned channel-planar PCM chunks and does not require temporary WAV export. The adapter must make Source and Base chunk boundaries identical and guarantee that Base is the final canonical Reader output mapped into the source PCM domain.

No implicit resampling, phase/time offset inference, channel remapping, playback gain, or normalization is performed in KRC.

## 4. KRM-IF v0.2 implementation boundary

The container stores:

- audio/timeline metadata;
- canonical interleaved Source/Base PCM SHA-256 digests;
- paired channel-planar signed-int64 Base and Raw Residual payloads;
- optional Base provenance metadata (descriptive only; not cryptographic proof of Reader origin);
- per-payload CRC-32C;
- aggregate Base/Residual payload SHA-256 digests.

Analysis, tracking, events, KRM-FC, journal, and KASF references are architecturally reserved but are not currently serialized as full blocks by the Python prototype.

## 5. Streaming behavior

- KRC reads or receives one block at a time.
- The container's block body is written once.
- CLI analysis reopens the KRM-IF and streams blocks; it does not concatenate full residual channels in memory.
- Auto-threshold analysis uses two sequential passes: one for P² median estimation, another for event grouping.
- Predictor demo preserves history across chunks and does not concatenate the full residual.

This is bounded by the configured block size plus rolling analysis window and event output. It is not a guarantee of constant memory for arbitrary event counts or metadata size.

## 6. Integrity policy

- Reject invalid manifest types/ranges before block reads.
- Verify exact file size and declared block geometry.
- Verify each payload's CRC-32C.
- Verify whole-source/Base PCM digests and whole payload digests.
- Reject Base samples outside the declared source PCM domain.
- Reject reconstructed samples outside the source PCM domain.
- Write to unique same-directory temporary files and atomically replace only after completion.

Draft 0.2 does not provide crash resume. An interrupted temporary file is uncommitted and must not be treated as a valid KRM-IF artifact.

## 7. Important unsolved integration work

1. Actual KASF Reader-to-chunk adapter.
2. Sample-for-sample proof between canonical Reader and any streaming Reader path, including OLA and global normalization.
3. Long-recording checkpoint/journal with resume and Revision commit.
4. KASF/KRM atomic candidate transaction coordinator.
5. Full analysis/event algorithms and serialized analysis blocks.
6. KRM-SIM state/innovation reproducibility design.
7. A finalized container format with explicit extension rules and independent interoperability tests.

## 8. Performance and memory note

The user's calculated workload estimate of KASF Rev.0.9.7 at about 55 hours versus Rev.0.9.20 at about 26 hours is context supplied by the user, not reproduced by this package. KRM should reuse KASF's completed analysis and not duplicate that workload. The direct chunk API is intended to avoid huge temporary WAV exports, but no KRM performance benchmark has yet been run.
