from __future__ import annotations
import random
import tempfile
import unittest
import wave
from pathlib import Path

from krm_proto.capture import capture_residual, capture_residual_chunks
from krm_proto.restore import restore_krmi, restore_raw_pcm, verify_krmi
from krm_proto.pcm import WavSpec
from tests.helpers import write_test_wav


class RoundTripTests(unittest.TestCase):
    def _values(self, width: int, count: int, seed: int) -> list[list[int]]:
        rng = random.Random(seed)
        if width == 1:
            lo, hi = -128, 127
        else:
            lo, hi = -(1 << (width * 8 - 1)), (1 << (width * 8 - 1)) - 1
        values = [lo, hi, 0, -1, 1]
        values.extend(rng.randint(lo, hi) for _ in range(max(0, count - len(values))))
        return values[:count]

    def test_pcm_widths_mono_and_stereo(self):
        for width in (1, 2, 3, 4):
            for channel_count in (1, 2):
                with self.subTest(width=width, channels=channel_count), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    count = 37
                    source_channels = [self._values(width, count, 100 + ch + width) for ch in range(channel_count)]
                    # Keep Base values within the Source PCM domain; residual may exceed it.
                    base_channels = [self._values(width, count, 200 + ch + width) for ch in range(channel_count)]
                    source_raw = write_test_wav(root / "source.wav", source_channels, 48000, width)
                    write_test_wav(root / "base.wav", base_channels, 48000, width)
                    capture_residual(root / "source.wav", root / "base.wav", root / "test.krmi", chunk_samples=9)
                    result = restore_krmi(root / "test.krmi", root / "restored.wav")
                    with wave.open(str(root / "restored.wav"), "rb") as restored:
                        restored_raw = restored.readframes(restored.getnframes())
                    self.assertEqual(source_raw, restored_raw)
                    self.assertEqual(result["matches_embedded_source_hash"], True)
                    self.assertEqual(verify_krmi(root / "test.krmi", root / "source.wav")["status"], "PASS")

    def test_payload_corruption_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = [[i - 20 for i in range(64)]]
            base = [[(i // 2) - 10 for i in range(64)]]
            write_test_wav(root / "source.wav", source, 44100, 2)
            write_test_wav(root / "base.wav", base, 44100, 2)
            capture_residual(root / "source.wav", root / "base.wav", root / "test.krmi", chunk_samples=32)
            blob = bytearray((root / "test.krmi").read_bytes())
            blob[-1] ^= 0x01
            (root / "corrupt.krmi").write_bytes(blob)
            with self.assertRaisesRegex(ValueError, "CRC-32C mismatch"):
                verify_krmi(root / "corrupt.krmi")

    def test_chunk_api_roundtrip_without_wav_intermediates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = WavSpec(channels=2, sample_rate=48000, sample_width=3, sample_count=7)
            source = [[-100, -50, 0, 1, 50, 100, 200], [200, 100, 50, 1, 0, -50, -100]]
            base = [[-90, -40, 0, 0, 40, 90, 190], [190, 90, 40, 0, 0, -40, -90]]
            source_chunks = [[ch[start:start + 3] for ch in source] for start in range(0, 7, 3)]
            base_chunks = [[ch[start:start + 3] for ch in base] for start in range(0, 7, 3)]
            capture_residual_chunks(source_chunks, base_chunks, spec, root / "chunks.krmi", chunk_samples=3)
            report = verify_krmi(root / "chunks.krmi")
            self.assertEqual(report["status"], "PASS")
            restore_krmi(root / "chunks.krmi", root / "restored.wav")
            with wave.open(str(root / "restored.wav"), "rb") as restored:
                self.assertEqual(restored.getnframes(), 7)
                self.assertEqual(restored.getnchannels(), 2)
                self.assertEqual(restored.getsampwidth(), 3)

    def test_raw_pcm_restore_matches_interleaved_source_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_channels = [[-32768, -1, 0, 1, 32767], [10, 20, 30, 40, 50]]
            base_channels = [[-32000, -5, 0, 5, 32000], [0, 0, 0, 0, 0]]
            source_raw = write_test_wav(root / "source.wav", source_channels, 44100, 2)
            write_test_wav(root / "base.wav", base_channels, 44100, 2)
            capture_residual(root / "source.wav", root / "base.wav", root / "test.krmi", chunk_samples=2)
            report = restore_raw_pcm(root / "test.krmi", root / "restored.pcm")
            self.assertEqual((root / "restored.pcm").read_bytes(), source_raw)
            self.assertEqual(report["interleaving"], "frame-interleaved")

    def test_base_provenance_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            spec = WavSpec(channels=1, sample_rate=48000, sample_width=2, sample_count=4)
            provenance = {
                "origin": "canonical_kasf_reader_pcm",
                "engine": "KASF",
                "engine_revision": "Rev.0.9.20",
                "reader_version": "1.2",
                "normalization_policy": "test-fixture",
                "alignment": "identity_in_input_pcm_domain",
            }
            capture_residual_chunks([[[1, 2, 3, 4]]], [[[0, 0, 0, 0]]], spec,
                                    root / "provenance.krmi", chunk_samples=4,
                                    base_provenance=provenance)
            from krm_proto.restore import inspect_krmi
            self.assertEqual(inspect_krmi(root / "provenance.krmi")["base_provenance"], provenance)

    def test_empty_pcm_stream_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "empty-source.wav"
            base_path = root / "empty-base.wav"
            write_test_wav(source_path, [[]], 48000, 2)
            write_test_wav(base_path, [[]], 48000, 2)
            capture_residual(source_path, base_path, root / "empty.krmi", chunk_samples=16)
            self.assertEqual(verify_krmi(root / "empty.krmi", source_path)["status"], "PASS")
            restore_krmi(root / "empty.krmi", root / "empty-restored.wav")

    def test_chunk_api_rejects_misaligned_block_sizes(self):
        with tempfile.TemporaryDirectory() as temp:
            spec = WavSpec(channels=1, sample_rate=48000, sample_width=2, sample_count=5)
            source_chunks = [[[1, 2]], [[3, 4, 5]]]
            base_chunks = [[[0, 0]], [[0, 0, 0]]]
            with self.assertRaisesRegex(ValueError, "sample count mismatch"):
                capture_residual_chunks(source_chunks, base_chunks, spec, Path(temp) / "bad.krmi", chunk_samples=3)

    def test_output_cannot_overwrite_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_path = root / "source.wav"
            write_test_wav(source_path, [[0, 1, 2, 3]], 48000, 2)
            write_test_wav(root / "base.wav", [[0, 0, 0, 0]], 48000, 2)
            original = source_path.read_bytes()
            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                capture_residual(source_path, root / "base.wav", source_path)
            self.assertEqual(source_path.read_bytes(), original)

    def test_mismatched_timeline_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_test_wav(root / "source.wav", [[0, 1, 2]], 48000, 2)
            write_test_wav(root / "base.wav", [[0, 1, 2]], 44100, 2)
            with self.assertRaises(ValueError):
                capture_residual(root / "source.wav", root / "base.wav", root / "bad.krmi")


if __name__ == "__main__":
    unittest.main()
