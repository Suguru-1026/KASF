# KASF FastGen Temporal Track Map — Draft 0.1

Status: experimental metadata sidecar. The default tracker does not alter KASF component values.

## 1. Purpose

FastGen originally performed independent per-frame spectral pursuit. The tracker adds a stable identity layer across adjacent frames so KRM can reason about evolving components, estimate event trajectories, and associate KRM-FC proposals without assuming that array position is a persistent identity.

## 2. Matching

Matching is channel-local and one-to-one. For each active track, the next-frame prediction uses recent frequency slope, expected phase advance, and previous amplitude. Candidate pairs outside a frequency gate are discarded. Remaining pairs are ranked by a deterministic cost combining normalized frequency error, circular phase error, and log-amplitude change. Sorted pairs are assigned greedily, so one old track and one new component can be assigned at most once per frame.

A track may survive two missing frames. Track IDs are local to a channel and generated in creation order, starting at 1. Track IDs are diagnostic identities, not claims about perceptual sources or instruments.

## 3. JSONL map

FastGen writes `<output.kasf>.tracks.jsonl` when tracking is enabled. There is one JSON object for every frame/channel pair:

```json
{"frame": 12, "channel": 0, "track_ids": [4, 8, 9]}
```

`track_ids[i]` corresponds to the i-th component in that channel of that KASF frame. FastGen's baseline sorts frame components by frequency before writing. The JSONL sidecar is hashed in the FastGen metadata sidecar. It is not embedded into KASF v1, preserving the 32-byte header and 6-byte component format.

## 4. Audio-payload invariant

Default temporal tracking is metadata-only. Given identical input and generation options, a tracking-enabled run and a `--no-tracking` run must write byte-identical KASF files and byte-identical Base WAV files. This is tested. The track map can therefore be used by KRM without changing the current KASF reconstruction or increasing Raw Residual merely because tracking is enabled.

## 5. Experimental refinement (not default)

`--experimental-track-refine` enables a phase-unwrapped average-frequency estimate and adjusts the component phase to preserve the fitted symmetric-window center. This modifies serialized component values. Current synthetic steady-tone, chirp, mixed-tone, and transient experiments showed Base SNR reductions in several cases. It is opt-in and must not be treated as a quality improvement or canonical setting. It remains available only for controlled experiments.

## 6. Limitations

- Greedy local matching can switch identities when components cross or closely approach one another.
- No global assignment, harmonic grouping, stereo linking, instrument/source identity, or perceptual confidence model.
- Track IDs can fragment when the spectral pursuit drops a component or when an attack changes phase/amplitude abruptly.
- The phase predictor is an association feature, not a phase correction policy in the default mode.
