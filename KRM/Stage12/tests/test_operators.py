import unittest
import numpy as np

from krm_td_csc.operators import adjoint, forward, inner_product_error


class TestDirectTimeOperators(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(19)
        self.atoms = []
        for length in (7, 16, 31):
            d = rng.normal(size=length)
            d /= np.linalg.norm(d)
            self.atoms.append(d)
        self.coeffs = [rng.normal(size=257 + d.size - 1) for d in self.atoms]

    def test_adjoint_identity(self):
        rng = np.random.default_rng(20)
        r = rng.normal(size=257)
        err = inner_product_error(self.coeffs, self.atoms, r)
        self.assertLess(err, 1e-10)

    def test_forward_boundary_cropping(self):
        atom = np.array([1.0, 0.0, 0.0])
        coeff = np.zeros(7)  # N=5 plus L-1=2 overlap positions
        coeff[-1] = 2.0
        y = forward([coeff], [atom], 5)
        np.testing.assert_array_equal(y, np.array([0, 0, 0, 0, 2.0]))

    def test_full_overlap_represents_atoms_crossing_both_boundaries(self):
        atom = np.array([1.0, 2.0, 3.0]) / np.sqrt(14.0)
        coeff = np.zeros(7)  # N=5, L=3; starts at -2 and +4
        coeff[0] = 1.0
        coeff[-1] = 2.0
        y = forward([coeff], [atom], 5)
        expected = np.array([3.0, 0.0, 0.0, 0.0, 2.0]) / np.sqrt(14.0)
        np.testing.assert_allclose(y, expected, rtol=0, atol=1e-14)

    def test_adjoint_matches_finite_difference(self):
        rng = np.random.default_rng(21)
        x = rng.normal(size=257)
        r = rng.normal(size=257)
        grad = adjoint(r, self.atoms)
        eps = 1e-6
        k, t = 1, 81
        plus = [a.copy() for a in self.coeffs]
        minus = [a.copy() for a in self.coeffs]
        t = 81
        plus[k][t] += eps
        minus[k][t] -= eps
        fp = float(np.dot(forward(plus, self.atoms, x.size), r))
        fm = float(np.dot(forward(minus, self.atoms, x.size), r))
        self.assertAlmostEqual((fp - fm) / (2 * eps), grad[k][t], places=6)
