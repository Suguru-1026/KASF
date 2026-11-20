# CHANGELOG — Rev0.9.19 Three-Worker Architecture

## Added
- Added dedicated Worker A / Worker B encoder instances.
- Added Worker C as the shared analysis worker by moving forward the former Worker B analysis workload.
- Added Stereo routing: A=right channel, B=left channel.
- Added Mono long-chunk frame partitioning between A and B.
- Added 350ms analysis guard context around Mono subranges and trim of duplicate guard output frames.
- Added internal Mono split seam phase linking based on A's trailing phase tracks.
- Added ordered channel-body merge helpers and guarded-body parsing/validation helpers.
- Added per-worker timing/report fields and a three-worker progress description.
- Added Node tests for channel merge, Mono split, resampling subrange equivalence, multichannel ordering and split-phase connection.

## Preserved
- KASF v1 file header/body encoding and component quantization.
- Reader v1.2 synthesis implementation.
- Existing VP/QR/Loss candidate evaluation and optimizer iteration counts.
- Existing final exact Reader evaluation and acceptance/rollback path.

## Routing policy
- Mono chunks >=1.5s and >=8 output frames: A/B split at an output-frame boundary.
- Short Mono chunks: A only.
- Stereo: A=right, B=left.
- 3 or more channels: retain the previous all-channel encoder route in A; C remains the shared analysis worker when enabled.

## Not included in this release
- Incremental/difference-only VP Reader evaluation.
- New VP basis oscillator or basis cache.
- New Multi-start seed strategy.
- KASE cross-method candidate evaluation cache.
- Any claim of measured end-to-end speedup or objectively improved sound quality.
