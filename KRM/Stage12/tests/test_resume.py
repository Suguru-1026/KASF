from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from krm_proto.capture import capture_residual_chunks
from krm_proto.pcm import WavSpec
from krm_proto.restore import verify_krmi


class ResumeCaptureTests(unittest.TestCase):
    def _chunks(self):
        source = [[i * 17 - 300 for i in range(13)], [200 - i * 11 for i in range(13)]]
        base = [[i * 5 - 40 for i in range(13)], [70 - i * 3 for i in range(13)]]
        source_chunks = [[channel[start:start + 4] for channel in source] for start in range(0, 13, 4)]
        base_chunks = [[channel[start:start + 4] for channel in base] for start in range(0, 13, 4)]
        return source_chunks, base_chunks

    def test_resume_after_stream_failure_and_truncate_uncommitted_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "resumable.krmi"
            source, base = self._chunks()
            spec = WavSpec(2, 48000, 2, 13)

            def source_breaks_after_first_block():
                yield source[0]
                raise RuntimeError("simulated interruption")

            with self.assertRaisesRegex(RuntimeError, "simulated interruption"):
                capture_residual_chunks(source_breaks_after_first_block(), iter(base), spec,
                                        output, chunk_samples=4)

            partial = root / "resumable.krmi.partial"
            journal = root / "resumable.krmi.journal.json"
            self.assertTrue(partial.exists())
            self.assertTrue(journal.exists())
            checkpoint = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["committed_blocks"], 1)
            committed_size = checkpoint["committed_size"]

            # Simulate a crash while a later block was being appended.
            with open(partial, "ab") as fp:
                fp.write(b"uncommitted-tail")

            manifest = capture_residual_chunks(iter(source), iter(base), spec, output,
                                               chunk_samples=4, resume=True)
            self.assertEqual(verify_krmi(output)["status"], "PASS")
            self.assertEqual(manifest["audio"]["sample_count"], 13)
            self.assertFalse(partial.exists())
            self.assertFalse(journal.exists())
            self.assertTrue(output.exists())
            self.assertGreater(committed_size, 0)

    def test_resume_rejects_changed_committed_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "changed.krmi"
            source, base = self._chunks()
            spec = WavSpec(2, 48000, 2, 13)

            def stop_after_first():
                yield source[0]
                raise RuntimeError("stop")

            with self.assertRaises(RuntimeError):
                capture_residual_chunks(stop_after_first(), iter(base), spec, output, chunk_samples=4)

            changed = [[list(channel) for channel in block] for block in source]
            changed[0][0][0] += 1
            with self.assertRaisesRegex(ValueError, "Source input differs"):
                capture_residual_chunks(iter(changed), iter(base), spec, output,
                                        chunk_samples=4, resume=True)

    def test_resume_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "optin.krmi"
            source, base = self._chunks()
            spec = WavSpec(2, 48000, 2, 13)

            def stop_after_first():
                yield source[0]
                raise RuntimeError("stop")

            with self.assertRaises(RuntimeError):
                capture_residual_chunks(stop_after_first(), iter(base), spec, output, chunk_samples=4)
            with self.assertRaisesRegex(FileExistsError, "resume=True"):
                capture_residual_chunks(iter(source), iter(base), spec, output, chunk_samples=4)

    def test_resume_after_manifest_patch_was_written_but_rename_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "finalizing.krmi"
            source, base = self._chunks()
            spec = WavSpec(2, 48000, 2, 13)
            from krm_proto import resumable
            original_patch = resumable.patch_file_manifest

            def patch_then_interrupt(fp, manifest, expected_length):
                original_patch(fp, manifest, expected_length)
                raise RuntimeError("simulated power loss after header patch")

            with patch("krm_proto.resumable.patch_file_manifest", side_effect=patch_then_interrupt):
                with self.assertRaisesRegex(RuntimeError, "after header patch"):
                    capture_residual_chunks(iter(source), iter(base), spec, output, chunk_samples=4)

            partial = root / "finalizing.krmi.partial"
            journal = root / "finalizing.krmi.journal.json"
            self.assertTrue(partial.exists())
            self.assertEqual(json.loads(journal.read_text(encoding="utf-8"))["phase"], "FINALIZING")

            capture_residual_chunks(iter(source), iter(base), spec, output,
                                    chunk_samples=4, resume=True)
            self.assertEqual(verify_krmi(output)["status"], "PASS")
            self.assertFalse(partial.exists())
            self.assertFalse(journal.exists())

    def test_resume_rejects_corrupt_journal(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "journal.krmi"
            source, base = self._chunks()
            spec = WavSpec(2, 48000, 2, 13)

            def stop_after_first():
                yield source[0]
                raise RuntimeError("stop")

            with self.assertRaises(RuntimeError):
                capture_residual_chunks(stop_after_first(), iter(base), spec, output, chunk_samples=4)
            journal = root / "journal.krmi.journal.json"
            journal.write_text(journal.read_text(encoding="utf-8").replace('"committed_blocks":1', '"committed_blocks":2'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "integrity check"):
                capture_residual_chunks(iter(source), iter(base), spec, output,
                                        chunk_samples=4, resume=True)


if __name__ == "__main__":
    unittest.main()
