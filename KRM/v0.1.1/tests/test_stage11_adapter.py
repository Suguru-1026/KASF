import tempfile
import unittest
from pathlib import Path

from krm_stage12 import Config, run_stage12, validate_input
from krm_stage12.stage11_adapter import build_normalized_input


def compact_fixture(cells, frame_count=4, bin_count=8, implicit='S0'):
    return {
        'schema_version': 'krm-stage11-normalized-1.1',
        'input_manifest': {
            'input_id': 'implicit-grid-test', 'sample_rate': 44100, 'fft_size': 2048,
            'hop_size': 512, 'window': 'hann', 'center_padding': 'none',
            'frame_timestamp_convention': 'center', 'frequency_bin_convention': 'rfft',
            'stage11_version': 'test', 'channel_id': 0, 'resolution_id': 'test-resolution',
            'frame_count': frame_count, 'bin_count': bin_count,
            'grid_complete': True, 'implicit_cell_state': implicit,
        },
        'cells': cells,
    }


class ImplicitS0GridTests(unittest.TestCase):
    def test_schema_10_missing_cells_remain_invalid(self):
        data = compact_fixture({'0,3': {'state': 'S2', 'power': 1e-3, 'delta_db': 14.0}})
        data['schema_version'] = 'krm-stage11-normalized-1.0'
        data['input_manifest'].pop('grid_complete')
        data['input_manifest']['implicit_cell_state'] = 'S0'
        # In schema 1.0, the undeclared extension cannot change the legacy rule.
        from krm_stage12.core import _state_map_from_input
        self.assertEqual(_state_map_from_input(data).get((1, 3)), 'INVALID')

    def test_sparse_complete_grid_uses_implicit_s0(self):
        data = compact_fixture({'0,3': {'state': 'S2', 'power': 1e-3, 'delta_db': 14.0}})
        validate_input(data)
        result = run_stage12(data, Config(s1_bridge_enabled=False))
        self.assertEqual(result['validation']['active_input_cells'], 1)
        self.assertTrue(result['validation']['cell_conservation'])
        self.assertEqual(result['validation']['input_grid_complete'], True)
        self.assertEqual(result['validation']['implicit_cell_state'], 'S0')
        self.assertEqual(result['features'][0]['feature_completeness'], 1.0)
        self.assertEqual(result['features'][0]['invalid_fraction'], 0.0)

    def test_schema_11_rejects_implicit_active_state_until_supported(self):
        data = compact_fixture({'0,3': {'state': 'S2', 'power': 1e-3, 'delta_db': 14.0}}, implicit='S2')
        with self.assertRaises(ValueError):
            validate_input(data)

    def test_explicit_invalid_is_not_silently_treated_as_implicit_s0(self):
        ring = {(0,0),(0,1),(0,2),(1,0),(1,2),(2,0),(2,1),(2,2)}
        cells = {f'{f},{b}': {'state':'S2','power':1e-3,'delta_db':14.0} for f,b in ring}
        cells['1,1'] = {'state':'INVALID'}
        data = compact_fixture(cells, frame_count=3, bin_count=3)
        result = run_stage12(data, Config(s1_bridge_enabled=False))
        feat = result['features'][0]
        self.assertAlmostEqual(feat['feature_completeness'], 8 / 9)
        self.assertAlmostEqual(feat['invalid_fraction'], 1 / 9)


class NativeStage11AdapterTests(unittest.TestCase):
    def test_reproduces_stage11_from_npz_and_maps_frequency_major_to_frame_major(self):
        try:
            import numpy as np
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest('NumPy/SciPy unavailable; install [stage11] extra')
        from krm_stage11.analysis.stage11_silence_typing import analyze_signal

        fs = 44100
        n = 8192
        t = np.arange(n, dtype=np.float64) / fs
        signal = 0.002 * np.sin(2 * np.pi * 880 * t)
        with tempfile.TemporaryDirectory() as td:
            npz = Path(td) / 'fixture.npz'
            np.savez(npz, R=signal[:, None])
            data = build_normalized_input(npz, 0)
            validate_input(data)
            f, ts, power, excess, typ, regions, stats = analyze_signal(signal)
            self.assertEqual(data['input_manifest']['frame_count'], len(ts))
            self.assertEqual(data['input_manifest']['bin_count'], len(f))
            self.assertEqual(data['stage11_reproduction']['class_counts'], stats['class_counts'])
            self.assertEqual(data['stage11_reproduction']['candidate_region_count'], len(regions))
            # A selected S2/S3 cell must map as frame,bin (transpose of Stage11's bin,frame arrays).
            nz = np.argwhere(typ >= 2)
            if len(nz):
                b, fr = map(int, nz[0])
                key = f'{fr},{b}'
                self.assertIn(key, data['cells'])
                self.assertEqual(data['cells'][key]['state'], f'S{int(typ[b, fr])}')
                self.assertAlmostEqual(data['cells'][key]['power'], float(power[b, fr]))

    def test_recovered_archive_both_channels_match_saved_summary(self):
        try:
            import numpy as np
            import scipy  # noqa: F401
        except ImportError:
            self.skipTest('NumPy/SciPy unavailable; install [stage11] extra')
        root = Path(__file__).resolve().parents[1]
        npz = root / 'research_archive' / 'stage08_reader_v12_aligned_arrays.npz'
        summary = root / 'krm_stage11' / 'outputs' / 'stage11_summary.json'
        for channel in (0, 1):
            data = build_normalized_input(npz, channel, summary_path=summary)
            counts = data['stage11_reproduction']['class_counts']
            self.assertTrue(data['stage11_reproduction']['parity_with_saved_stage11_summary'])
            self.assertEqual(data['input_manifest']['frame_count'], 1459)
            self.assertEqual(data['input_manifest']['bin_count'], 1025)
            self.assertEqual(data['stage11_reproduction']['cells_total'], 1495475)
            self.assertEqual(sum(counts.values()), 1495475)
            del data


if __name__ == '__main__':
    unittest.main()
