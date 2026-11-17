import unittest
import numpy as np

from krm_td_csc.operators import forward
from krm_td_csc.solver import solve_cbpdn_fista
from krm_td_csc.admm import solve_cbpdn_admm


class TestSolvers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(7)
        cls.atoms = []
        for length in (12, 24, 48, 24):
            d = rng.normal(size=length)
            d /= np.linalg.norm(d)
            cls.atoms.append(d)
        n = 512
        coefficients = [np.zeros(n + d.size - 1) for d in cls.atoms]
        for a, d in zip(coefficients, cls.atoms):
            for p in rng.choice(np.arange(20, n - 80), size=4, replace=False):
                a[p + d.size - 1] = rng.uniform(0.3, 1.0) * rng.choice([-1.0, 1.0])
        cls.signal = forward(coefficients, cls.atoms, n)

    def test_fista_decreases_objective_monotonically(self):
        result = solve_cbpdn_fista(self.signal, self.atoms, lam=0.001, max_iterations=180)
        self.assertGreater(result.objective_history[0], result.objective_history[-1])
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(result.objective_history, result.objective_history[1:])))
        self.assertGreater(10 * np.log10(np.sum(self.signal**2) / np.sum(result.residual**2)), 35.0)

    def test_admm_converges_on_sparse_synthetic_case(self):
        result = solve_cbpdn_admm(
            self.signal, self.atoms, lam=0.001, rho=0.3,
            max_iterations=400, cg_tolerance=1e-6, cg_max_iterations=100,
            abs_tolerance=2e-6, rel_tolerance=2e-5,
        )
        self.assertTrue(result.converged)
        self.assertGreater(10 * np.log10(np.sum(self.signal**2) / np.sum(result.residual**2)), 50.0)
        self.assertEqual(len(result.rho_history), result.iterations)

    def test_fista_and_admm_reach_similar_objective(self):
        fista = solve_cbpdn_fista(self.signal, self.atoms, lam=0.002, max_iterations=1200, tolerance=1e-6)
        admm = solve_cbpdn_admm(self.signal, self.atoms, lam=0.002, rho=0.1, max_iterations=300)
        self.assertTrue(fista.converged)
        self.assertTrue(admm.converged)
        self.assertLess(fista.optimality_residual, 1e-6 * max(1.0, np.sqrt(sum(np.dot(a, a) for a in fista.coefficients))))
        self.assertLess(abs(fista.objective_history[-1] - admm.objective_history[-1]), 1e-3)

    def test_zero_lambda_reduces_residual(self):
        result = solve_cbpdn_fista(self.signal, self.atoms, lam=0.0, max_iterations=120)
        self.assertLess(np.linalg.norm(result.residual), np.linalg.norm(self.signal))
