# Version migration — KASF v3.0 Rev.0.2.2

- Product-facing version: `KASF v3.0 Rev.0.2.2`.
- Saved artifact filename tag: `v3-R0-2-2`.
- Updated the primary HTML title, visible heading, lead, footer, and current package documentation.
- Updated KASF, KCP, and JSON export names to include the save tag.
- New OPFS checkpoint metadata includes `productVersion`, `productRevision`, and `saveTag`.
- Preserved KASF v1 binary serialization, Reader v1.2, and the `KASF-KCP-1` checkpoint format identifier.
- Preserved the OPFS directory name `KASF_Rev099` to avoid orphaning checkpoints saved by earlier builds.
- Rev0.9.x labels inside the feature descriptions are historical feature-lineage labels and are intentionally retained.

## Validation after version migration

- `bash build-validate.sh`: PASS; embedded WASM verified at 17,706 bytes with the existing SHA-256.
- `tests/test-html-script-syntax.cjs`: PASS (6 executable script blocks).
- 28 deterministic `test-*.cjs` files: PASS individually, including the three-worker edge-case test (run separately).
- `test-short-approx-stress.cjs`: not run; it remains the excluded long-running stress test.
- The migration changes product-facing labels, output filenames, and checkpoint metadata only. It does not change the KASF v1 binary serialization or Reader v1.2.
