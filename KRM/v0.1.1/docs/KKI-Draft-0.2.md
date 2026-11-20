# KKI — KASF/KRM Interface Draft 0.2

Status: protocol design baseline. No transport or KASF integration is implemented in this package.

## 1. Purpose

KKI is the exchange contract between KASF and KRM. It prevents either engine from depending on the other's internal memory layout or private data structures.

## 2. Packet families

| Family | Direction | Purpose |
|---|---|---|
| Audio Reference | KASF → KRM | Source/Base/Residual references and timeline identity |
| Analysis Metadata | Both | Track, event, HPSS/STN, confidence and provenance data |
| Frequency Candidate (KRM-FC) | KRM → KASF | Proposed KASF-compatible component descriptions |
| Evaluation Result | KASF → KRM | Accepted/rejected/staged and measured outcomes |
| Revision Control | Both / Coordinator | Parent revisions, trial IDs, commit/rollback |

Audio PCM payloads and metadata should be separate. A classification label must never silently alter Raw Residual samples.

## 3. KRM-FC fields

Required proposal fields:

- candidate ID
- parent KASF revision ID
- parent residual revision ID
- source event ID (if event-derived)
- start and end sample indices (end exclusive)
- center frequency in Hz
- amplitude and phase
- chirp rate in Hz/s
- bandwidth in Hz
- confidence in `[0,1]`
- analysis algorithm/version and parameter provenance
- optional per-frame KASF component proposal array
- explicit phase reference sample/time

KRM-FC values are proposed estimates. They are not yet quantized KASF component values and are not guaranteed to fit KASF's 24-bit frequency / 14-bit amplitude / 10-bit phase fields.

## 4. Candidate state machine

```text
PROPOSED
  → RECEIVED
  → PREFLIGHT
  → STAGED
  → SYNTHESIZING
  → QUALITY_CHECK
  → KRM_VERIFY
  → COMMITTED
```

Failure states:

- `REJECTED`: invalid, unsupported, or quality policy rejects the proposal before commit.
- `ROLLED_BACK`: a trial was staged but failed synthesis, integrity, or exact reconstruction checks.
- `DEFERRED`: KASF requires more evidence or cannot decide yet.

## 5. Acceptance protocol

1. Verify parent KASF and residual revision IDs. Stale candidates must not be applied blindly.
2. Check candidate values, sample interval, Nyquist range, channel mapping, phase reference, and KASF representability.
3. Apply the candidate only to an isolated trial copy.
4. Optionally use applicable existing KASF optimization (including KASE-2.1); do not assume every event can map to a sinusoidal KASF component.
5. Quantize and serialize using the actual KASF v1 path.
6. Re-read with the actual Reader version and run exact Reader synthesis.
7. Evaluate waveform, spectral, envelope, attack, and stability safeguards.
8. Ask KRC to create a new full residual from Source minus trial Base.
9. Verify exact integer PCM reconstruction and all integrity data.
10. Commit KASF and KRM revisions together. On any failure, retain the previous revision.

Approximate local resynthesis may rank candidates, but cannot authorize final acceptance.

## 6. Two-phase commit

KASF acceptance is not a committed state.

- Phase A: trial staging, synthesis, residual capture, full verification.
- Phase B: atomically update the manifest/commit pointer for both engines.

No one-sided commit is permitted. Immutable prior revisions remain available for rollback.

## 7. Information exchanged from KASF to KRM

Useful optional metadata:

- KASF component frequency/amplitude/phase after quantization
- Generator track identifiers and trajectories, if tapped before packing
- MRA report and region-level diagnostics
- Reader version, synthesis window, normalization and sample-domain mapping
- component lineage and parent revision

These records do not replace Base PCM or Raw Residual.

## 8. Information returned from KRM to KASF

- KRM-FC frequency/event candidates
- estimated confidence and parameter uncertainty
- event support interval and channel association
- reason for proposal and analysis provenance
- optional diagnostic that a component seems unrepresentable in current KASF form

KASF retains final authority over its own Component representation, subject to the joint exact-reconstruction commit protocol.
