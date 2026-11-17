import unittest
import numpy as np
from krm_td_csc.dictionary import initialize_dictionary_from_signal


class TestDictionaryInit(unittest.TestCase):
    def test_multiscale_normalised_atoms(self):
        rng = np.random.default_rng(1)
        x = rng.normal(size=1024)
        atoms = initialize_dictionary_from_signal(x, scales=(16, 32, 64), atoms_per_scale=3, seed=8)
        self.assertEqual(len(atoms), 9)
        self.assertEqual(sorted(set(a.size for a in atoms)), [16, 32, 64])
        for atom in atoms:
            self.assertAlmostEqual(np.linalg.norm(atom), 1.0, places=10)

    def test_short_signal_skips_too_long_scales(self):
        x = np.sin(np.arange(64) * 0.2)
        atoms = initialize_dictionary_from_signal(x, scales=(16, 32, 128), atoms_per_scale=2)
        self.assertTrue(all(a.size in (16, 32) for a in atoms))

    def test_silent_signal_rejected(self):
        with self.assertRaises(ValueError):
            initialize_dictionary_from_signal(np.zeros(256))
