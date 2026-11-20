# KASF v3.0 preparatory hardening — KASE-2.1 / JARS

Status: KASF v3.0 Rev.0.2.2 development component; not a final/stable release. It does not change the KASF v1 wire format or Reader.

## Source baseline

- Encoder source: `KASF-v3.0-Rev0.2.2.html`
- Source package lineage: Rev.0.9.19 three-worker / Rev.0.9.20 temporal guards
- Existing WASM binary and its exports are unchanged.
- Existing storage implementation and the three storage paths are unchanged.

## Changes

### KASE-2.1 bounded CMA-ES

1. Candidate steps used by covariance adaptation now correspond to the **evaluated, clipped coordinates**. Previously, candidate positions were clipped to `[-1, 1]` for evaluation while covariance adaptation used the unclipped Gaussian sample. Near a boundary, those were different points and the covariance update could learn from a step that had never been evaluated.
2. The rank-μ update now uses the same effective bounded steps.
3. The update stops rather than adapting from an incomplete elite set when fewer than μ finite candidates remain. The CMA-ES learning rates assume a complete μ-sized elite group.
4. Stagnation is now counted by generations without a new global best, rather than by a small mean displacement or a small change in path norm.
5. The returned algorithm label now describes the implemented bounded variant accurately; it no longer calls the modified implementation canonical CMA-ES.

### KASE-C2

- When invalid candidate scores reduce the elite set, the retained rank weights are renormalized before calculating the mean and empirical covariance. This prevents missing elite weight from implicitly pulling the mean toward the origin.

### JARS joint acceptance gate

- Rejects mismatched input lengths, invalid sample rates, and non-finite source / baseline / candidate values.
- Rejects non-finite waveform metrics and non-finite spectral scores.
- This closes a fail-open case where a `NaN` spectral score could bypass the `newScore > oldScore` comparison and be treated as acceptable.

## Regression test

Added `tests/test-kase21-jars-hardening.cjs`.

It checks:
- bounded quadratic convergence for KASE-2.1;
- deterministic output for a fixed seed;
- safe handling of an all-NaN objective;
- bounded, finite results from KASE-C2 and jDE;
- JARS rejection of mismatched inputs and non-finite spectral metrics;
- JARS acceptance of a finite improving candidate.

## Verification

- Focused KASE/JARS regression: PASS.
- Existing deterministic tests: 27 pre-existing test files (excluding the long-running `test-short-approx-stress.cjs`) were exercised. 25 passed in the initial batch; the two three-worker tests initially lacked their required HTML-path argument, then both passed when rerun with that argument.
- New KASE/JARS regression test: PASS.
- The earlier WASM build-pipeline fix remains included in this package; this patch does not alter the WASM binary.
- Long-running stress test, real-audio listening comparison, browser execution on Chromebook, and Emscripten production rebuild were not performed as part of this patch.

## Compatibility

- KASF v1 output format: unchanged.
- Reader v1.2: unchanged.
- Existing three storage methods and KCP checkpoint behavior: unchanged.
- Worker orchestration and WASM binary: unchanged.
- The patch changes only optimization candidate adaptation and JARS candidate admission safeguards.
