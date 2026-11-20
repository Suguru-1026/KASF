# KRC Crash Recovery — Draft 0.3

Status: implemented in the Python prototype. The KRM-IF on-disk container remains revision `prototype-0.2`; this describes the KRC writer's sidecar checkpoint behavior.

## 1. Checkpoint files

For output path `capture.krmi`, the writer uses:

- `capture.krmi.partial` — append-only in-progress KRM-IF file;
- `capture.krmi.journal.json` — small atomic checkpoint record.

The completed `.krmi` appears only after the manifest digest fields are finalized and the partial file is atomically renamed.

## 2. Per-block commit order

For each Base/Residual block:

1. Validate synchronized Source and Base input chunk geometry and PCM domain.
2. Compute `R = X - B` in the integer domain.
3. Append a complete block containing Base and Residual payloads plus CRC-32C values.
4. Flush and `fsync()` the partial container.
5. Write a new journal to a unique temporary file, flush and `fsync()` it, then atomically replace the previous journal.
6. Best-effort `fsync()` the parent directory.

The journal's `committed_size` and `committed_blocks` therefore refer only to blocks whose file data was flushed first. A crash during an uncommitted append leaves a tail beyond the last journaled size.

## 3. Journal integrity and recovery

The journal includes a schema version, destination filename, capture-header SHA-256, committed block/sample counts, committed file size, capture phase, and (during finalization) final manifest. The journal payload is protected by SHA-256 over canonical JSON.

On resume, KRC:

1. Confirms both checkpoint files exist and the journal is valid.
2. Checks the requested output and capture configuration against the saved header identity.
3. Confirms the partial file is not shorter than the committed size.
4. Truncates any bytes beyond the last committed size.
5. Replays Source and Base iterators from sample zero.
6. Verifies every committed block's geometry and CRC-32C.
7. Compares replayed Base samples and recomputed `Source - Base` against the stored committed block.
8. Rebuilds all SHA-256 hashers from the verified prefix rather than attempting to serialize Python hash state.
9. Continues with the first uncommitted block.

This replay check prevents a checkpoint from being continued with changed Source samples, a different Reader output, a changed normalization profile, or different Base data. A caller-provided Base provenance object is also part of the initial header identity.

## 4. Finalization protocol

After all declared blocks are committed and both input iterators are confirmed to have no extra chunks:

1. Compute final Source, Base, Base-payload, and Residual-payload SHA-256 values.
2. Atomically commit a `FINALIZING` journal containing the complete final manifest.
3. Patch the fixed-length manifest in the partial KRM-IF file and `fsync()` it.
4. Atomically rename `.partial` to the requested `.krmi` destination.
5. Remove the journal and best-effort sync the parent directory.

If power is lost after the final manifest patch but before the rename, resume accepts either the original placeholder header or the already-patched final header, replays and validates the input prefix, and finishes finalization.

## 5. API behavior

`capture_residual_chunks(..., resume=False)` and the WAV convenience `capture_residual(..., resume=False)` create checkpoints automatically. If an exception interrupts capture, the partial and journal files are retained.

To continue, call the same API with `resume=True` and provide **fresh Source and Base iterators beginning at sample zero**. The previously committed prefix is re-read for verification. A new run refuses to overwrite an existing checkpoint unless `resume=True` is explicit.

CLI example:

```bash
python -m krm_proto capture \
  --source source.wav \
  --base canonical-reader-base.wav \
  --output capture.krmi \
  --chunk-samples 65536 \
  --resume
```

Do not pass `--resume` on the first run unless intentionally creating a new capture with resume enabled; a missing checkpoint simply starts a new capture.

## 6. Limits and guarantees

- One writer per output path is supported; concurrent writers are not coordinated.
- Recovery requires both sidecar files. A missing or corrupt journal is rejected rather than guessed.
- The input streams must be replayable from sample zero. A one-shot non-repeatable stream cannot resume.
- Replaying a large committed prefix costs time proportional to the already-completed portion. This is the deliberate trade-off for verifying the input has not changed without serializing private hash state.
- `fsync()` and atomic rename semantics depend on the filesystem and operating system. This prototype does not claim protection against every storage-device cache or filesystem failure mode.
- This is a KRC capture journal, not the KASF OPFS/KCP journal and not the KKI cross-engine revision transaction.
- The journal is not yet serialized as a block in KRM-IF. It remains an adjacent recovery file and is removed after successful completion.
