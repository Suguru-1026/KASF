# Tests

Run all deterministic tests from this directory:

```sh
for f in test-*.cjs; do node "$f" || exit 1; done
```

Run the approximate Reader benchmark separately:

```sh
node bench-short-approx-reader.cjs
```

Tests compare the exact Reader path and Hybrid outputs against the Rev.0.9.17 reference HTML under `../comparison/`. Approximate mode is expected to differ by tiny floating-point amounts during scoring; the Hybrid integration tests also verify the exact final output and final metrics on their deterministic fixtures.

## Rev0.9.20 Temporal Guards

```bash
node tests/test-temporal-guards.cjs KASF-v3.0-Rev0.2.2.html
```

This deterministic unit test covers stable-track phase innovation limits, one-frame phase-spike correction, attack bypass, musical-noise attenuation limits, harmonic/persistence protection, and no-delete/OFF behavior.
