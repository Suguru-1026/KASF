# KAS(KASF)
## Kinoko Audio Structure (File)
*Experimental Audio Encoding, Compression and Reconstruction Project*

> Project documentation / README
> Documentation date: 2026-11-22

## Web Tools
Note: The HTML interface is currently available in Japanese only.

### KASF Reader
- [Reader v1.2](https://suguru-1026.github.io/KASF/reader/)

### KASF Generator
- [Generator v2.0 — Published page (page identifies itself as Rev.0.9.20 + OPFS Manager)](https://suguru-1026.github.io/KASF/v2.0_rev.0.9.21/)
- [Generator v3.0 — Public Web build (Rev.0.2.2)](https://suguru-1026.github.io/KASF/v3.0/Rev.0.2.2/)

---
# 1. Project Overview

KASF is an experimental audio encoding and reconstruction project.

Its primary objective is to represent audio through frequency-domain components rather than relying exclusively on conventional PCM sample storage.

The project explores:
- Frequency-domain audio analysis
- Spectral component extraction
- Predictive component tracking
- Frequency, amplitude and phase representation
- Phase continuity and reconstruction
- Audio compression and storage efficiency
- Parallel processing
- Reliable intermediate storage and recovery

KASF is developed incrementally, with experimental revisions, regression testing and explicitly maintained baselines.

## 1.1 Project Status

| Component | Current status |
|---|---|
| KASF v1 | Original format generation |
| KASF v2.0 | Fixed baseline |
| KASF v2.0 Rev.0.9.21 | Official fixed baseline |
| KASF v3.0 | Active development |
| KASF v3.0 Rev.0.2.12 | Latest internal development revision |
| KASF v3.0 Web Generator | Public Web build: Rev.0.2.2 |
| KRM v1.1.0 | Canonical KRM reference package; independently versioned |

**Current development target:** KASF v3.0 Rev.0.2.12

**Latest fixed v2.0 baseline:** KASF v2.0 Rev.0.9.21

**Current public v3.0 Web build:** KASF v3.0 Rev.0.2.2

The latest internal development revision and the public Web build are tracked separately. The public Web build has not been updated to every internal development revision.

---
# 2. Project Architecture

KASF has three major conceptual stages:

1. Audio analysis
2. Component encoding
3. Audio reconstruction

The encoding process extracts relevant frequency components and represents them using a compact binary structure.

The reconstruction process interprets those components and generates an audio signal.

The architecture has evolved considerably between v1 and v2.

---

# 3. KASF v1 — Original Generation
## 3.1 Overview

KASF v1 established the original component-based audio representation.

Its principal characteristics include:

- Custom binary format
- 32-byte file header
- 48-bit audio components
- Multichannel support
- Variable component count per frame
- 50% frame overlap
- Independent Generator and Reader

## 3.2 Binary Structure
### Header

The original header occupies 32 bytes.

Known fields include:

| Field | Description |
|---|---|
| Magic | File identification (`KSAF`) |
| Version | Format version |
| Channels | Number of audio channels |
| Frames | Frame count |
| Frame Duration | Frame duration |

The exact byte offsets and serialization details belong to the binary format specification.

### Component Representation

Each component occupies 6 bytes (48 bits).

| Field | Bit width |
|---|---:|
| Frequency | 24 bits |
| Amplitude | 14 bits |
| Phase | 10 bits |
| Total | 48 bits |

Components represent individual spectral elements.

The number of components is not fixed per frame.

## 3.3 Original Processing Pipeline

The original Generator uses the following processing stages:

1. PCM input
2. 50% overlapping frame segmentation
3. Periodic Hann window
4. Zero-padded radix-2 FFT
5. Local spectral peak detection
6. Parabolic interpolation
7. Component tracking
8. Phase continuity processing
9. KASF binary output

The Reader uses periodic Hann windowing and 50% overlap-add reconstruction.

Phase values are referenced to the beginning of each frame.

## 3.4 Historical Test Results

An early v1 test processed approximately 249 seconds of stereo audio.

| Measurement | Result |
|---|---:|
| Original data size | 5.2 MB |
| KASF output | 8.22 MB |
| Frame count | 24,938 |
| Average components | 26.13 / channel / frame |
| Component size | 6 bytes |

This demonstrated that the original representation could reconstruct audio, but it was not consistently storage-efficient.

The difference between original and encoded sizes motivated further compression research.

---
# 4. KASF v2.0 — Advanced Encoding Generation

## 4.1 Overview

KASF v2.0 builds upon the original component representation.

Its development focuses on improving component tracking, frequency estimation, phase behavior and overall processing architecture.

The v2 generation retains compatibility with the KASF v1 binary representation and Reader architecture.

## 4.2 Major Technical Features
### Predictive Tracking

Predictive Tracking estimates component behavior between successive frames.

The tracking system considers:

- Frequency
- Frequency movement
- Amplitude
- Previous component state
- Component continuity

The objective is to reduce unnecessary component replacement and improve temporal consistency.

### Phase Continuity

Phase processing is used to maintain more consistent reconstructed waveforms across frames.

### High-Frequency Tracking Compensation

Additional tracking compensation was introduced to improve the handling of higher-frequency components.

### Amplitude Compensation

Band-dependent amplitude compensation was explored to address differences in spectral representation across frequency ranges.

### Multiresolution FFT

Multiresolution analysis was incorporated into the v2 development line to investigate frequency resolution and component detection.

---
# 5. v2.0 Development History

The following records describe important development stages, not necessarily separate public releases.

## 5.1 Early v2 Experiments

Early v2 work investigated:

- Predictive Tracking improvements
- TCE-S / TCE-C processing
- Component selection and representation
- Compatibility with the original Reader

An early TVS implementation successfully produced KASF v1-compatible output.

A one-second test generated 99 frames and was successfully decoded by the unmodified Reader.

Missing and excess frame counts were both zero in that test.

However, UI operation and the claimed audio-quality improvements were not fully verified.

## 5.2 Rev.0.9.5 — Predictive Phase Research

PPR (Predictive Phase Reconstruction) was investigated.

This method used three neighboring frames:

- Previous frame
- Current frame
- Next frame

Householder QR was used for joint phase estimation.

The important design constraint was that frequency and amplitude remained unchanged. Only phase was modified.

The selection process evaluated reconstruction SSE after quantization and Reader-side reconstruction.

Recorded synthetic reconstruction results:

| Metric | Before | After |
|---|---:|---:|
| NMSE | 0.05863 | 0.001772 |

This represents approximately 97% reduction in the measured NMSE.

An actual Worker test also evaluated 207 locations across 24 points.

These results belong to the specific PPR experiment and should not be interpreted as universal audio-quality improvements.

## 5.3 Audio Quality Experiments

Several revisions investigated reconstruction quality.

Experiments included:

- Frequency component selection
- Phase reconstruction
- Amplitude compensation
- Low-frequency representation
- High-frequency tracking
- Component tracking adjustments

Earlier revisions demonstrated that improving one frequency range could negatively affect another.

For example, some experimental configurations improved bass reproduction but blurred piano transients and weakened short percussive sounds.

This remains an important consideration in future development.

## 5.4 Rev.0.9.21 — Fixed Baseline

KASF v2.0 Rev.0.9.21 is the officially fixed v2.0 baseline.

Its encoding lineage is based on the Rev.0.9.19 generation, with additional storage and recovery hardening.

### Encoding Architecture

- Three-Worker integration
- Worker C for common input analysis
- Worker A for independent encoding
- Worker B for independent encoding
- KASF v1-compatible output
- Reader v1.2 compatibility

### Input

The implemented input processing path supports:

- WAV
- MP3
- OGG
- FLAC

Actual decoding availability depends on the browser's supported audio decoding capabilities.

### Storage Architecture

The fixed baseline includes:

- OPFS-based storage
- KCP intermediate storage
- CRC-32C integrity checking
- Metadata size limit of 8 MiB
- Dual checkpoint generations
- Journal-based recovery
- Chunk validation
- Interrupted-processing recovery

### Recovery and Reliability Improvements

Important changes include:

1. `nextChunk === records.length` is required for consistency.
2. Independent A/B checkpoint validation.
3. Fallback to an older checkpoint when the latest generation is corrupted.
4. Two-bank `active.a` / `active.b` storage.
5. KCP validation before expansion into the inactive storage area.
6. CRC-32C verification.
7. Protection of uncommitted data.
8. Web Locks-based exclusion control.
9. No silent fallback from OPFS to Blob storage.
10. Recovery immediately before completion.

### RAM Budget Handling

RAM budget settings are preserved for diagnostics.

However, RAM budget changes alone do not invalidate resume compatibility.

Resume rejection is tied to changes in actual chunk boundaries or `effectiveSpan`, rather than diagnostic memory-budget settings.

### Regression Testing

Rev.0.9.21 passed all six recorded regression tests.

These tests included simulated OPFS behavior.

**Important:** Passing simulated regression tests does not establish successful long-duration operation on every physical device.

A full real-device long-duration verification was not completed as part of the baseline validation.

---
# 6. Performance and Compression Evaluation

KASF evaluates compression through both storage efficiency and reconstruction quality.

A smaller output file is not sufficient evidence of a successful encoding method.

The following measurements are relevant:

- Input size
- Output size
- Compression ratio
- Frequency response
- Reconstruction error
- Phase consistency
- Perceptual audio quality
- Processing time
- Memory consumption
- Storage reliability

## 6.1 Historical v2 Test

A historical test used a stereo WAV file with the following characteristics:

| Parameter | Value |
|---|---:|
| Sample rate | 48 kHz |
| Channels | 2 |
| Duration | 249.38 seconds |
| WAV size | 87.3 MB |
| KASF size | 77.6 MB |

The encoded file was smaller than the original WAV.

However, the tested reconstruction exhibited audible differences, including muffled sound and weaker bass reproduction.

This is a historical experimental result, not a guaranteed performance figure for Rev.0.9.21.

The compression ratio alone does not establish perceptual transparency.

---
# 7. File Format and Compatibility

Primary file extension:

`.kasf`

The original v1 format uses:

- 32-byte header
- 48-bit components
- Variable component counts
- Multichannel representation
- Frame-based organization

KASF v2.0 preserves the established v1 output format.

### Compatibility

| Feature | Status |
|---|---|
| KASF v1 binary representation | Supported |
| Reader v1.2 compatibility | Supported |
| v2 encoding architecture | Implemented |
| v3 binary format | Not yet specified |

The exact binary serialization specification should be maintained separately from this README.

---
# 8. KRM Relationship

KRM is a related project with its own independent versioning.

The canonical KRM reference package is:

`KRM_Complete_v1.1.0.zip`

KRM v1.1.0 remains independently versioned. Its Python implementation is the reference implementation for the corresponding KRM processing stages; the browser-side KRM code in KASF is a separate integration/port.

### KASF v2.0

KRM is not formally integrated into the fixed KASF v2.0 baseline.

### KASF v3.0

KASF v3.0 includes experimental browser-side KRM integration. The implemented paths include:

- External `.krmi` input with its matching original WAV
- External `.kasf` input with its matching original WAV
- KRM-IF v0.1 / v0.2 block-based reading and validation
- Stage11 normalized JSON generation
- Stage11 normalized JSON preview in the Workbench
- Stage12 browser-side processing integration

For KRM-IF v0.1 / v0.2, the browser reader validates data in blocks rather than expanding the entire container into one large in-memory array. The Stage11 standard profile remains distinct from the experimental segmented full-range profile; segmented analysis can produce different results from one-pass analysis.

The KASF Reader-based `.kasf` path uses the matching WAV for sample-rate and sample-count information. Exact parity with every final normalization/quantization step of the full KASF application export path has not been established. The input provenance and validation state should therefore remain explicit in generated data.

These integrations apply to the KASF v3 development line and do not imply that KRM is integrated into KASF v2.0. Other KRM subsystems, including KRM-FC / SIM, should be treated as separate unless their integration is independently implemented and validated.

---
# 9. KASF v3.0 — Current Development

**Current internal development revision: KASF v3.0 Rev.0.2.13**

**Development started:** 2026-11-17

**Current public Web build:** Rev.0.2.2 (tracked separately from the latest internal development revision)

KASF v3.0 represents the next major development generation.

The v2.0 baseline remains fixed and available as the reference implementation.

### Current Development Areas

- Preserve KASF v1 binary output and Reader compatibility where applicable.
- Maintain the v3 storage layer and its independently tracked baseline.
- Integrate browser-side KRM input and Stage11 / Stage12 processing paths.
- Support chunk-based validation and reading for KRM-IF v0.1 / v0.2.
- Provide Stage11 normalized JSON generation and Workbench preview.
- Keep the Stage11 standard profile distinguishable from experimental segmented full-range analysis.
- Keep KCP compatibility handling explicit when transferring or resuming work across v2/v3 revisions.
- Keep the user-facing layout aligned with the public Rev.0.2.2 interface while retaining newer internal processing controls.

### KCP and Cross-Version Compatibility

KASF v3 includes compatibility handling for legacy v2 KCP settings. The KCP1 container format is kept distinct from the newer internal engine configuration.

Settings that can be represented by the v2 configuration can be mapped for compatibility checks. A v3-only combination that has no equivalent in v2 must not be silently mapped to a different v2 mode; resume compatibility should be rejected when the processing semantics cannot be preserved.

### Development Rules

- Preserve the v2.0 baseline.
- Clearly distinguish implemented functionality from planned functionality.
- Record experimental results with their corresponding revisions.
- Avoid treating unverified improvements as established facts.
- Maintain data integrity throughout development.
- Document format compatibility explicitly.

### v3.0 Specification

Detailed v3.0 architecture and format specifications continue to evolve.

No unconfirmed feature should be presented as an implemented v3.0 capability.

---
# 10. Known Limitations

KASF has several areas requiring continued investigation.

### Audio Quality

- Frequency-dependent reconstruction differences
- Low-frequency representation
- Transient preservation
- Phase reconstruction accuracy
- Reconstruction artifacts

### Processing

- High computational requirements
- Memory consumption
- Long-running Worker stability
- Chunk processing overhead
- Stage11 segmented analysis is experimental and is not numerically identical to one-pass full-range analysis

### Storage

- Interrupted processing
- Checkpoint consistency
- Recovery behavior
- Storage quota limitations
- OPFS availability

### Compatibility

- Browser-dependent input decoding
- Reader compatibility
- Future format evolution
- Exact full-application export parity for the KASF Reader-based Stage11 input path has not been established

---
# 11. Development Philosophy

KASF follows these principles:

**1. Experimental verification**

Implementations must be evaluated through actual tests.

**2. Data integrity**

Encoded data and intermediate results must be protected against corruption.

**3. Compatibility**

Existing format compatibility should be preserved unless a deliberate format transition is introduced.

**4. Resource awareness**

Memory, processing time and storage limitations are fundamental engineering considerations.

**5. Reproducibility**

Experimental results should be associated with exact revisions and test conditions.

**6. Clear development status**

Implemented, tested, experimentally evaluated and planned features must remain distinguishable.

---
# 12. Project Timeline

| Date | Milestone |
|---|---|
| 2026-09-19 | Original KASF v1 architecture documented |
| 2026-09-19 | Initial binary format and component processing experiments |
| 2026-10-26 | v2.0 TVS and related experiments |
| 2026-11-10 | PPR phase reconstruction research |
| 2026-11-15 | Storage recovery and reliability improvements |
| 2026-11-17 | v2.0 Rev.0.9.21 fixed |
| 2026-11-17 | KRM-v1 Rev.0.1.0 fixed |
| 2026-11-17 | v3.0 Rev.0.1.0 development started |
| 2026-11-22 | v3.0 internal development reached Rev.0.2.12 |
| 2026-11-22 | KRM-IF block-based input and Stage11 normalized JSON Workbench integration documented |

---
# 13. Terminology

| Term | Meaning |
|---|---|
| KASF | Project name |
| Component | Individual frequency-domain audio element |
| Frame | A unit of audio analysis |
| Generator | Audio encoder |
| Reader | Audio reconstruction component |
| PPR | Predictive Phase Reconstruction |
| OPFS | Origin Private File System |
| KCP | KASF-related intermediate/checkpoint storage mechanism |
| CRC-32C | Data integrity checksum |
| Worker A/B | Independent encoding Workers |
| Worker C | Common input analysis Worker |
| KRM-IF | KRM interchange format used for Base / Residual data exchange |
| Stage11 | KRM analysis stage producing normalized analysis data |
| Stage12 | KRM follow-up processing stage |

---
**KASF Project Documentation**

Version: README Draft 3
Documentation date: 2026-11-22
Current development: KASF v3.0 Rev.0.2.12
Current public v3.0 Web build: Rev.0.2.2
Fixed reference: KASF v2.0 Rev.0.9.21
