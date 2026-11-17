import math
import struct
import tempfile
import unittest
from pathlib import Path

from krm_proto.kasf_reader import iter_reader_pcm_chunks, read_header, reader_geometry


def pack_component(frequency, amplitude, phase):
    qf = max(0, min(0xFFFFFF, math.floor(frequency / 96000 * 0xFFFFFF + 0.5)))
    qa = max(0, min(0x3FFF, math.floor(amplitude * 0x3FFF + 0.5)))
    phase = phase % (2 * math.pi)
    qp = max(0, min(1023, math.floor(phase / (2 * math.pi) * 1024 + 0.5)))
    value = qf | (qa << 24) | (qp << 38)
    return value.to_bytes(6, 'little')


def write_kasf(path, channels, frame_duration, frames):
    with open(path, 'wb') as fp:
        fp.write(struct.pack('<4sIQQd', b'KASF', 1, channels, len(frames), frame_duration))
        for frame in frames:
            for channel in frame:
                fp.write(struct.pack('<Q', len(channel)))
                for comp in channel:
                    fp.write(pack_component(*comp))


class KASFReaderTests(unittest.TestCase):
    def test_geometry_uses_reader_rounding_not_frame_size_half(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.kasf'
            write_kasf(p, 1, 0.005, [[[]], [[]]])
            with p.open('rb') as fp:
                h = read_header(fp)
            self.assertEqual(reader_geometry(h, 44100, 221), (221, 110))

    def test_streamed_ola_matches_direct_reference(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.kasf'
            rate, duration, count = 8000, 0.001, 20
            frames = [
                [[(440.0, .4, .2), (880.0, .1, 1.1)]],
                [[(445.0, .3, .5)]],
                [[(220.0, .2, -.3)]],
                [[(330.0, .15, 2.2)]],
            ]
            write_kasf(p, 1, duration, frames)
            n, h = 8, 4
            expected = [0.0] * count
            for m, frame in enumerate(frames):
                for local_n in range(n):
                    sample = m * h + local_n
                    if sample >= count: break
                    total = 0.0
                    for f, a, phase in frame[0]:
                        qf = math.floor(f / 96000 * 0xFFFFFF + 0.5) * 96000 / 0xFFFFFF
                        qa = math.floor(a * 0x3FFF + 0.5) / 0x3FFF
                        qp = math.floor((phase % (2*math.pi)) / (2*math.pi) * 1024 + 0.5)
                        qp = min(1023, max(0, qp))
                        qp = qp * 2*math.pi/1024
                        total += qa * math.sin(2*math.pi*qf*local_n/rate + qp)
                    w = .5 - .5*math.cos(2*math.pi*local_n/n)
                    expected[sample] += w * total
            chunks = list(iter_reader_pcm_chunks(p, sample_rate_hz=rate, sample_count=count, chunk_samples=3))
            actual = [x for chunk in chunks for x in chunk[0]]
            self.assertEqual(len(actual), count)
            for a, b in zip(actual, expected):
                self.assertAlmostEqual(a, b, places=13)

    def test_stereo_planar_and_chunk_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.kasf'
            frames = [[[ (440,.2,0) ], [ (660,.3,.4) ]], [[(441,.2,.1)],[(661,.3,.5)]]]
            write_kasf(p, 2, .002, frames)
            chunks = list(iter_reader_pcm_chunks(p, sample_rate_hz=8000, sample_count=24, chunk_samples=5))
            self.assertTrue(all(len(c)==2 for c in chunks))
            self.assertEqual(sum(len(c[0]) for c in chunks),24)
            self.assertNotEqual([v for c in chunks for v in c[0]], [v for c in chunks for v in c[1]])

    def test_rejects_trailing_bytes_and_uncovered_timeline(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.kasf'
            write_kasf(p, 1, .001, [[[]]])
            with p.open('ab') as fp: fp.write(b'X')
            with self.assertRaises(ValueError):
                list(iter_reader_pcm_chunks(p, sample_rate_hz=8000, sample_count=8))
            write_kasf(p, 1, .001, [[[]]])
            with self.assertRaises(ValueError):
                list(iter_reader_pcm_chunks(p, sample_rate_hz=8000, sample_count=9))

    def test_rejects_invalid_component_count(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x.kasf'
            with open(p, 'wb') as fp:
                fp.write(struct.pack('<4sIQQd', b'KASF', 1, 1, 1, .001))
                fp.write(struct.pack('<Q', 100001))
            with self.assertRaises(ValueError):
                list(iter_reader_pcm_chunks(p, sample_rate_hz=8000, sample_count=8))

    def test_rejects_transposed_magic_typo(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'bad.kasf'
            with open(p, 'wb') as fp:
                fp.write(struct.pack('<4sIQQd', b'KFSA', 1, 1, 1, .001))
            with p.open('rb') as fp:
                with self.assertRaisesRegex(ValueError, 'KASF magic'):
                    read_header(fp)


if __name__ == '__main__':
    unittest.main()
