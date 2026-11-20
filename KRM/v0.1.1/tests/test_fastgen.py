import json
import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import krm_proto.fastgen as fastgen_module
from krm_proto.capture import capture_residual_chunks
from krm_proto.pcm import decode_interleaved, read_wav_spec
from krm_proto.fastgen import build_native, generate_and_capture, generate_kasf, render_kasf_to_base_wav
from krm_proto.kasf_reader import _iter_frames, read_header
from krm_proto.restore import restore_krmi, verify_krmi


class FastGenIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (shutil.which('g++') or shutil.which('clang++')):
            raise unittest.SkipTest('C++17 compiler not installed')
        cls.temp_build = tempfile.TemporaryDirectory()
        cls.binary = build_native(Path(cls.temp_build.name) / 'kasf_fastgen')

    @classmethod
    def tearDownClass(cls):
        cls.temp_build.cleanup()

    def _make_source(self, path: Path, seconds=1.5):
        rate = 8000
        count = int(rate * seconds)
        with wave.open(str(path), 'wb') as dst:
            dst.setnchannels(2)
            dst.setsampwidth(2)
            dst.setframerate(rate)
            raw = bytearray()
            for i in range(count):
                t = i / rate
                left = 0.36 * math.sin(2 * math.pi * 440.0 * t + 0.31) + 0.18 * math.sin(2 * math.pi * 997.0 * t + 0.80)
                right = 0.24 * math.sin(2 * math.pi * 523.25 * t - 0.40) + 0.12 * math.sin(2 * math.pi * 1300.0 * t + 0.20)
                raw.extend(struct.pack('<hh', max(-32768, min(32767, round(left * 32768))),
                                       max(-32768, min(32767, round(right * 32768)))))
            dst.writeframes(raw)
        return rate, count

    def test_native_generator_writes_real_kasf_magic_and_recovers_tones(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            rate, count = self._make_source(source)
            output = root / 'out.kasf'
            result = generate_kasf(source, output, frame_ms=100, max_components=12,
                                   threshold_db=-50, min_hz=10, edge_pad=True, binary=self.binary)
            with output.open('rb') as fp:
                header = read_header(fp)
                frames = list(_iter_frames(fp, header))
            self.assertEqual(header.channels, 2)
            self.assertEqual(result['magic'], 'KASF')
            self.assertEqual(header.frame_count, result['frame_count'])
            self.assertEqual(result['edge_padding_samples'], 400)
            self.assertEqual(result['analysis_timeline_sample_count'], count + 800)
            # The two strongest components in each channel should track the input tones.
            for ch, expected in ((0, (440.0, 997.0)), (1, (523.25, 1300.0))):
                observed = []
                for frame in frames:
                    observed.extend((amp, freq) for freq, amp, _phase in frame[ch] if amp > 0.05)
                self.assertGreater(len(observed), 10)
                top = sorted(observed, reverse=True)[:max(4, len(observed)//5)]
                mean_freq = sum(freq for _amp, freq in top) / len(top)
                # Most top-strength entries are the lower/higher steady partials;
                # aggregate via nearest expected tone rather than requiring ordering.
                self.assertTrue(all(min(abs(freq - x) for x in expected) < 2.0 for _amp, freq in top))
            meta = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
            self.assertEqual(meta['reader_bridge']['normalization'], 'none applied; the local Reader is pre any external/global normalization policy')

    def test_native_base_wav_matches_python_reader_quantized_pcm(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source)
            kasf = root / 'out.kasf'
            native_base = root / 'base-native.wav'
            python_base = root / 'base-python.wav'
            result = generate_kasf(source, kasf, frame_ms=100, max_components=12,
                threshold_db=-50, min_hz=10, edge_pad=True,
                base_wav=native_base, binary=self.binary)
            self.assertTrue(result['base_wav']['base_wav_sha256'])
            ref = render_kasf_to_base_wav(kasf, source, python_base)
            with wave.open(str(native_base), 'rb') as a, wave.open(str(python_base), 'rb') as b:
                self.assertEqual(a.getparams(), b.getparams())
                self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))
            self.assertEqual(ref['normalization'], 'none')
            self.assertFalse(result['base_wav']['base_is_official_kasf_pcm_export'])

    def test_native_base_wav_pcm_widths_8_24_32_match_python_reference(self):
        for width in (1, 3, 4):
            with self.subTest(sample_width=width), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                source = root / 'source.wav'
                rate, count = 8000, 4000
                scale = 1 << (width * 8 - (1 if width > 1 else 0))
                raw = bytearray()
                for i in range(count):
                    value = int(round(0.31 * math.sin(2 * math.pi * 437.0 * i / rate) * scale))
                    if width == 1:
                        raw.append(max(0, min(255, value + 128)))
                    else:
                        raw.extend(value.to_bytes(width, 'little', signed=True))
                with wave.open(str(source), 'wb') as dst:
                    dst.setnchannels(1); dst.setsampwidth(width); dst.setframerate(rate)
                    dst.writeframes(raw)
                kasf = root / 'out.kasf'
                native_base = root / 'base-native.wav'
                python_base = root / 'base-python.wav'
                generate_kasf(source, kasf, frame_ms=50, max_components=8,
                    threshold_db=-55, min_hz=20, edge_pad=True,
                    base_wav=native_base, binary=self.binary)
                render_kasf_to_base_wav(kasf, source, python_base)
                with wave.open(str(native_base), 'rb') as a, wave.open(str(python_base), 'rb') as b:
                    self.assertEqual(a.getparams(), b.getparams())
                    self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))

    def test_native_reader_base_uses_independent_odd_frame_hop_rounding(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'odd-geometry.wav'
            rate, count = 44100, 11025
            with wave.open(str(source), 'wb') as dst:
                dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(rate)
                raw = bytearray()
                for i in range(count):
                    value = 0.3 * math.sin(2 * math.pi * 997.0 * i / rate + 0.13)
                    raw.extend(struct.pack('<h', max(-32768, min(32767, round(value * 32768)))))
                dst.writeframes(raw)
            kasf = root / 'odd.kasf'
            native_base = root / 'odd-native.wav'
            python_base = root / 'odd-python.wav'
            stats = generate_kasf(source, kasf, frame_ms=5, max_components=8,
                threshold_db=-55, min_hz=20, edge_pad=True, base_wav=native_base, binary=self.binary)
            self.assertEqual(stats['frame_size'], 221)
            self.assertEqual(stats['hop_samples'], 110)
            render_kasf_to_base_wav(kasf, source, python_base)
            with wave.open(str(native_base), 'rb') as a, wave.open(str(python_base), 'rb') as b:
                self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))

    def test_temporal_track_map_keeps_stable_id_without_changing_kasf_or_base(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'steady.wav'
            rate, count = 8000, 8000
            with wave.open(str(source), 'wb') as dst:
                dst.setnchannels(1)
                dst.setsampwidth(2)
                dst.setframerate(rate)
                raw = bytearray()
                for i in range(count):
                    value = 0.30 * math.sin(2 * math.pi * 440.0 * i / rate + 0.17)
                    raw.extend(struct.pack('<h', max(-32768, min(32767, round(value * 32768)))))
                dst.writeframes(raw)

            no_track_kasf = root / 'no-track.kasf'
            tracked_kasf = root / 'tracked.kasf'
            no_track_base = root / 'no-track.wav'
            tracked_base = root / 'tracked.wav'
            no_track = generate_kasf(
                source, no_track_kasf, frame_ms=50, max_components=1,
                threshold_db=-60, min_hz=20, edge_pad=True,
                temporal_tracking=False, base_wav=no_track_base, binary=self.binary,
            )
            tracked = generate_kasf(
                source, tracked_kasf, frame_ms=50, max_components=1,
                threshold_db=-60, min_hz=20, edge_pad=True,
                temporal_tracking=True, base_wav=tracked_base, binary=self.binary,
            )

            # Tracking is metadata-only by default. It must not silently modify
            # KASF component payloads or the rendered Base PCM.
            self.assertEqual(no_track_kasf.read_bytes(), tracked_kasf.read_bytes())
            with wave.open(str(no_track_base), 'rb') as a, wave.open(str(tracked_base), 'rb') as b:
                self.assertEqual(a.getparams(), b.getparams())
                self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))

            metadata = json.loads(Path(tracked['metadata']).read_text(encoding='utf-8'))
            track_info = metadata['track_map']
            self.assertEqual(track_info['format'], 'KASF-TrackMap-JSONL-v1')
            rows = [json.loads(line) for line in Path(track_info['path']).read_text(encoding='utf-8').splitlines()]
            self.assertEqual(len(rows), tracked['frame_count'])
            track_ids = [row['track_ids'][0] for row in rows]
            self.assertEqual(len(set(track_ids)), 1)
            self.assertGreater(tracked['temporal_matches'], 0)
            self.assertEqual(tracked['temporal_tracks_created'], 1)
            self.assertFalse(metadata['generator']['temporal_tracking']['experimental_refinement_enabled'])

    def test_hungarian_tracker_is_deterministic_and_payload_neutral(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'steady.wav'
            rate, count = 8000, 8000
            with wave.open(str(source), 'wb') as dst:
                dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(rate)
                raw = bytearray()
                for i in range(count):
                    value = 0.30 * math.sin(2 * math.pi * 440.0 * i / rate + 0.17)
                    raw.extend(struct.pack('<h', max(-32768, min(32767, round(value * 32768)))))
                dst.writeframes(raw)

            outputs = {}
            for mode in ('greedy', 'hungarian', 'hungarian-repeat'):
                kasf = root / f'{mode}.kasf'
                base = root / f'{mode}.wav'
                assignment = 'greedy' if mode == 'greedy' else 'hungarian'
                result = generate_kasf(
                    source, kasf, frame_ms=50, max_components=1,
                    threshold_db=-60, min_hz=20, edge_pad=True,
                    temporal_tracking=True, tracker_assignment=assignment,
                    base_wav=base, binary=self.binary,
                )
                metadata = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
                self.assertEqual(metadata['generator']['temporal_tracking']['assignment'], assignment)
                track_path = Path(metadata['track_map']['path'])
                outputs[mode] = (kasf.read_bytes(), base.read_bytes(), track_path.read_bytes())

            # Assignment affects only diagnostic track IDs, never KASF/Base audio.
            self.assertEqual(outputs['greedy'][0], outputs['hungarian'][0])
            self.assertEqual(outputs['greedy'][1], outputs['hungarian'][1])
            self.assertEqual(outputs['hungarian'][0], outputs['hungarian-repeat'][0])
            self.assertEqual(outputs['hungarian'][1], outputs['hungarian-repeat'][1])
            self.assertEqual(outputs['hungarian'][2], outputs['hungarian-repeat'][2])
            ids = [json.loads(line)['track_ids'][0] for line in outputs['hungarian'][2].decode().splitlines()]
            self.assertEqual(len(set(ids)), 1)

    def test_invalid_tracker_assignment_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source, seconds=0.1)
            with self.assertRaisesRegex(ValueError, 'tracker_assignment must be greedy or hungarian'):
                generate_kasf(source, root / 'out.kasf', tracker_assignment='nearest')

    def test_temporal_refinement_is_explicitly_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source, seconds=0.25)
            output = root / 'refined.kasf'
            result = generate_kasf(
                source, output, frame_ms=50, max_components=4,
                threshold_db=-55, min_hz=15, temporal_tracking=True,
                temporal_refinement=True, binary=self.binary,
            )
            metadata = json.loads(Path(result['metadata']).read_text(encoding='utf-8'))
            self.assertTrue(result['temporal_refinement_enabled'])
            self.assertTrue(metadata['generator']['temporal_tracking']['experimental_refinement_enabled'])

    def test_peak_search_ignores_energy_below_minimum_frequency(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'low_and_mid.wav'
            rate, count = 8000, 8000
            with wave.open(str(source), 'wb') as dst:
                dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(rate)
                raw = bytearray()
                for i in range(count):
                    t = i / rate
                    value = 0.35 * math.sin(2 * math.pi * 7.0 * t) + 0.22 * math.sin(2 * math.pi * 440.0 * t)
                    raw.extend(struct.pack('<h', max(-32768, min(32767, round(value * 32768)))))
                dst.writeframes(raw)
            output = root / 'out.kasf'
            generate_kasf(source, output, frame_ms=100, max_components=8,
                threshold_db=-55, min_hz=30, edge_pad=True, binary=self.binary)
            with output.open('rb') as fp:
                header = read_header(fp)
                frames = list(_iter_frames(fp, header))
            found = [f for frame in frames for f in frame[0] if abs(f[0] - 440.0) < 2.0]
            self.assertGreater(len(found), 0, 'A strong sub-minimum low tone must not block in-band peak search')

    def test_bridge_resumes_krc_without_regenerating_kasf_or_base(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source)
            kasf = root / 'out.kasf'
            base = root / 'base.wav'
            krmi = root / 'residual.krmi'
            real_capture = fastgen_module.capture_residual

            def interrupt_after_first_block(source_path, base_path, output_path, chunk_samples,
                                            *, base_provenance=None, resume=False):
                if resume:
                    return real_capture(source_path, base_path, output_path, chunk_samples,
                                        base_provenance=base_provenance, resume=True)
                with wave.open(str(source_path), 'rb') as src, wave.open(str(base_path), 'rb') as base_wav:
                    spec = read_wav_spec(src)
                    def source_chunks():
                        raw = src.readframes(chunk_samples)
                        if raw:
                            yield decode_interleaved(raw, spec)
                        raise RuntimeError('simulated interruption after one committed block')
                    def base_chunks():
                        raw = base_wav.readframes(chunk_samples)
                        if raw:
                            yield decode_interleaved(raw, spec)
                        raise RuntimeError('simulated interruption after one committed block')
                    return capture_residual_chunks(source_chunks(), base_chunks(), spec,
                        output_path, chunk_samples, base_provenance=base_provenance, resume=False)

            with patch.object(fastgen_module, 'capture_residual', side_effect=interrupt_after_first_block):
                with self.assertRaisesRegex(RuntimeError, 'simulated interruption'):
                    generate_and_capture(source, kasf, base, krmi, frame_ms=100,
                        max_components=12, threshold_db=-50, min_hz=10,
                        chunk_samples=997, binary=self.binary)
            self.assertTrue(Path(str(krmi) + '.partial').is_file())
            self.assertTrue(Path(str(krmi) + '.journal.json').is_file())
            from krm_proto.fastgen import sha256_file
            kasf_hash, base_hash = sha256_file(kasf), sha256_file(base)
            with patch.object(fastgen_module, 'capture_residual', real_capture):
                result = generate_and_capture(source, kasf, base, krmi, frame_ms=100,
                    max_components=12, threshold_db=-50, min_hz=10,
                    chunk_samples=997, resume=True, binary=self.binary)
            self.assertEqual(result['status'], 'CAPTURED_EXACT_RESIDUAL')
            self.assertEqual(sha256_file(kasf), kasf_hash)
            self.assertEqual(sha256_file(base), base_hash)
            self.assertFalse(Path(str(krmi) + '.partial').exists())
            self.assertFalse(Path(str(krmi) + '.journal.json').exists())
            check = verify_krmi(krmi, source)
            self.assertTrue(check.get('valid', check.get('status') in ('PASS', 'VALID')))

    def test_bridge_resume_rejects_changed_track_map(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source, seconds=0.3)
            kasf = root / 'out.kasf'
            base = root / 'base.wav'
            krmi = root / 'residual.krmi'
            real_capture = fastgen_module.capture_residual

            def interrupt_after_first_block(source_path, base_path, output_path, chunk_samples,
                                            *, base_provenance=None, resume=False):
                if resume:
                    return real_capture(source_path, base_path, output_path, chunk_samples,
                                        base_provenance=base_provenance, resume=True)
                with wave.open(str(source_path), 'rb') as src, wave.open(str(base_path), 'rb') as base_wav:
                    spec = read_wav_spec(src)
                    def source_chunks():
                        raw = src.readframes(chunk_samples)
                        if raw:
                            yield decode_interleaved(raw, spec)
                        raise RuntimeError('simulated interruption after one committed block')
                    def base_chunks():
                        raw = base_wav.readframes(chunk_samples)
                        if raw:
                            yield decode_interleaved(raw, spec)
                        raise RuntimeError('simulated interruption after one committed block')
                    return capture_residual_chunks(source_chunks(), base_chunks(), spec,
                        output_path, chunk_samples, base_provenance=base_provenance, resume=False)

            with patch.object(fastgen_module, 'capture_residual', side_effect=interrupt_after_first_block):
                with self.assertRaisesRegex(RuntimeError, 'simulated interruption'):
                    generate_and_capture(source, kasf, base, krmi, frame_ms=50,
                        max_components=8, threshold_db=-55, min_hz=15,
                        chunk_samples=257, binary=self.binary)

            track_map = Path(str(kasf) + '.tracks.jsonl')
            self.assertTrue(track_map.is_file())
            with track_map.open('ab') as fp:
                fp.write(b'{"tampered":true}\n')
            with self.assertRaisesRegex(ValueError, 'Temporal track map is missing or changed'):
                generate_and_capture(source, kasf, base, krmi, frame_ms=50,
                    max_components=8, threshold_db=-55, min_hz=15,
                    chunk_samples=257, resume=True, binary=self.binary)

    def test_fastgen_reader_krc_full_bridge_restores_source_exactly(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / 'source.wav'
            self._make_source(source)
            kasf, base, krmi, restored = (root / name for name in ('out.kasf', 'base.wav', 'residual.krmi', 'restored.wav'))
            result = generate_and_capture(source, kasf, base, krmi, frame_ms=100,
                max_components=12, threshold_db=-50, min_hz=10, tracker_assignment="hungarian", chunk_samples=997,
                force=False, binary=self.binary)
            check = verify_krmi(krmi, source)
            self.assertTrue(check.get('valid', check.get('status') in ('PASS', 'VALID')))
            self.assertEqual(result['status'], 'CAPTURED_EXACT_RESIDUAL')
            self.assertEqual(result['reader_bridge']['edge_padding_samples_each_side'], 400)
            self.assertEqual(result['generator']['base_wav']['renderer'], 'C++ FastGen embedded KASF05_Reader-equivalent OLA loop')
            bridge_meta = json.loads(Path(result['generator']['metadata']).read_text(encoding='utf-8'))
            self.assertEqual(bridge_meta['generator']['temporal_tracking']['assignment'], 'hungarian')
            self.assertEqual(result['krm_container']['block_count'], 13)  # 12,000 samples / 997-sample blocks
            restored_result = restore_krmi(krmi, restored)
            with wave.open(str(source), 'rb') as a, wave.open(str(restored), 'rb') as b:
                self.assertEqual(a.getparams(), b.getparams())
                self.assertEqual(a.readframes(a.getnframes()), b.readframes(b.getnframes()))
            with open(krmi, 'rb') as fp:
                from krm_proto.container import read_file_header
                manifest, _header, _size = read_file_header(fp)
            self.assertEqual(manifest['base_provenance']['engine'], 'KASF Fast Baseline Generator')
            self.assertEqual(manifest['base_provenance']['temporal_tracker_assignment'], 'hungarian')
            self.assertEqual(manifest['base_provenance']['integer_pcm_quantizer'].split(':')[0], 'KRM-PROTO-PCM-Q-v1')


if __name__ == '__main__':
    unittest.main()
