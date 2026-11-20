# KASF FastGen Temporal Tracking — Draft 0.2

Date: 2026-11-14

## Purpose

Temporal tracking assigns channel-local diagnostic identities to the per-frame components produced by KASF FastGen. It does not identify instruments, separate sources, or alter the audio by default. The output is a JSONL sidecar whose `track_ids` array follows the sorted component order in the corresponding KASF frame/channel record.

## Association modes

### Greedy (default)

The tracker computes admissible track/component pairs and sorts them by local cost. It accepts the lowest-cost pair when neither the track nor component has already been assigned in that frame. Ties are resolved deterministically by track index and component index.

Advantages: low overhead and simple behaviour. Limitation: an early locally-best pair can prevent a better total assignment for the rest of the frame.

### Hungarian (optional)

`--tracker-assignment hungarian` selects a rectangular minimum-cost one-to-one assignment for all active tracks and current-frame components in that channel.

- Admissible pair costs use the same predicted-frequency, phase-advance, and amplitude-continuity score as Greedy.
- Each track gets an independent dummy column with cost `1.120001`, slightly above the maximum admissible pair score (`1.12`), allowing the solver to leave a track unmatched.
- Components not assigned to an existing track start new IDs.
- The assignment is global only within one channel and one frame; it is not a multi-frame global optimizer.
- The solver is capped at 256 active tracks and 256 components/channel/frame to bound its assignment matrix and runtime. Use Greedy for larger component limits.
- Deterministic input order and tie handling make repeated runs reproducible with the same build and settings.

Hungarian can reduce local assignment conflicts, but it does not solve decomposition instability. In two real-audio comparisons it reduced the total number of created IDs and extended some of the longest tracks, but median track lengths remained short. It also increased generator runtime. Therefore Greedy remains the default; Hungarian is an experiment for analysis workflows.

## CLI / API

```bash
python -m krm_proto.fastgen generate \
  --input source.wav --output output.kasf \
  --tracker-assignment hungarian
```

Equivalent bridge option:

```bash
python -m krm_proto bridge-fast \
  --source source.wav --kasf output.kasf \
  --base base.wav --krmi capture.krmi \
  --tracker-assignment hungarian
```

Python API: `generate_kasf(..., tracker_assignment="hungarian")` or `generate_and_capture(..., tracker_assignment="hungarian")`.

Metadata records the selected assignment mode. KRC Base provenance also records `temporal_tracker_assignment`.

## Audio-payload invariant

Both assignment solvers operate after spectral-pursuit component extraction and before KASF frame serialization, but the default path uses the results only to produce the sidecar track IDs. The solver does not write back to component frequency, amplitude, or phase. With identical generation parameters, Greedy and Hungarian therefore produce byte-identical KASF component files and byte-identical native local-Reader Base WAVs. Tests verify this invariant.

The separate `--experimental-track-refine` option can alter frequency/phase values. It is not a tracking-only mode and is not recommended as a default; earlier synthetic tests showed Base-SNR regressions in several cases.

## Known limitations

- Frequency/phase estimates can jump when framewise residual pursuit changes which partials are selected.
- Close components, crossings, attacks, decays, and low-SNR residual peaks can create ID splits or swaps.
- Current lifetime is local: an unmatched track can survive up to two missing frames before being retired.
- No harmonic-group, timbral, stereo-coherence, or multi-hypothesis model is used.
- IDs are not guaranteed to correspond to a physical oscillator, note, instrument, or source.
- The track map is a diagnostic sidecar; it is not embedded in KASF v1 and is not required for Base reconstruction or exact KRM restoration.
