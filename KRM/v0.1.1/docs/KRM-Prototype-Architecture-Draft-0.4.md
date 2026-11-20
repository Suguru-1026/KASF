# KRM Prototype Architecture — Draft 0.4

- Package version: 0.4.0
- Physical KRM-IF: prototype-0.2 (unchanged)
- New module: `kasf_reader.py`

## Added boundary

The KASF v1 diagnostic reader parses the final saved KASF byte stream and reproduces the audited local Reader v1.2 overlap-add equation into bounded-memory float64 chunks. It consumes sample rate and output sample count as explicit side metadata because neither is in the 32-byte KASF v1 header. It never repeats phase joining; the final saved component bytes already contain seam adjustments.

## Deliberate non-goals

- No claim of canonical KASF full-file Reader parity.
- No invented global normalization.
- No invented float-to-integer quantizer.
- No KRM capture from diagnostic float64 output.
- No KASF source modification.

The next gate is to obtain/define the canonical KASF Reader PCM export and canonical Source PCM export, then establish the shared integer sample domain.
