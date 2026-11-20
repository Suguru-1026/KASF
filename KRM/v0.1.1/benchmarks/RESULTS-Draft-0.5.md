# Draft 0.5 Benchmark and Validation Results

Date: 2026-11-14. Measurements are from the current Linux execution environment.

## Workload

Synthetic RIFF/WAVE: 10 seconds, 48,000 Hz, 2 channels, signed 16-bit PCM. Each channel contains three sinusoidal/chirped components. No real music or speech was used.

## Native generator and KRM bridge

| Metric | Result |
|---|---:|
| FastGen frame-loop timer | 0.80960091 s |
| FastGen + native Base process wall time | 0.82 s |
| Full FastGen → native Base → KRC capture wall time (measured inside Python) | 4.29595071 s |
| Audio duration / FastGen process wall time | 12.20× |
| Frames | 2,001 |
| Components | 21,041 |
| KASF bytes | 158,294 |
| Base WAV bytes | 1,920,044 |
| KRM-IF bytes | 15,362,942 |
| Source/Base SNR | 51.8664 dB |
| First 100 ms SNR | 48.9730 dB |
| Last 100 ms SNR | 49.5074 dB |

The outer `/usr/bin/time` script also ran KRM verification and WAV restoration; it reported 10.80 seconds for the complete Python script. Do not mix that time with the 4.296-second measured bridge stage.

## Reader comparisons

The Rev.0.9.20 HTML's actual `KASF05_Reader` implementation was extracted and run by Node. Its float64 output was compared with `krm_proto.kasf_reader` for the same KASF file and 480,480 samples/channel including guard timeline:

- 960,960 values compared.
- Maximum absolute difference: `2.220446049250313e-16`.
- Mean absolute difference: `2.5901627633556662e-18`.
- 73,084 values were not bit-identical as float64; the difference is consistent with floating-point transcendental rounding.

The native C++ Base WAV was byte-identical to the Python reference Base WAV for this 48 kHz stereo / 16-bit case (1,920,000 PCM bytes), and for synthetic 8-, 16-, 24-, and 32-bit PCM cases in the unit tests.

## Exact KRC result

`verify_krmi` returned `PASS`:

- 960,000 channel samples checked.
- Source PCM SHA-256 and reconstructed PCM SHA-256 both `aa27ab31cb5d3d6e9b5c93468ee0771c3ecb55e4aa79066573ca7108ddd49709`.
- Supplied Source WAV matched the embedded source digest.
- Restored Source WAV PCM frame bytes were identical to the original.

This is exactness for the Source/Base pair captured by this prototype. It is not a claim of lossless KASF encoding without residual.

## Automated verification

- `python -m unittest discover -s tests -v`: **40/40 passed**.
- `python -m compileall -q krm_proto tests examples`: passed.
- C++17 compile with `-O3 -std=c++17 -ffp-contract=off -DNDEBUG -Wall -Wextra -Wpedantic`: passed.
- Native/Python Base PCM parity at 8/16/24/32-bit: passed.
- KRC interrupted-capture resume reuses the same KASF and Base files without re-running FastGen: passed.
- KASF v1 magic `KASF`; transposed `KFSA` rejected.
- Full FastGen → Base → KRC → KRM-IF → verify → restore pipeline: passed.
