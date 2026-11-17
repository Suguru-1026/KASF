import unittest
import numpy as np

from krm_td_csc.dictionary import initialize_dictionary_from_signal
from krm_td_csc.learning import (
    dictionary_gradient,
    dictionary_learning_objective,
    dictionary_smooth_loss,
    learn_convolutional_dictionary,
)
from krm_td_csc.operators import forward


class TestConvolutionalDictionaryLearning(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(401)
        self.atoms = []
        for _ in range(3):
            d = rng.normal(size=12)
            d *= np.hanning(12)
            d /= np.linalg.norm(d)
            self.atoms.append(d)
        self.signals = []
        self.true_maps = []
        for sample_index in range(4):
            maps = [np.zeros(128 + 12 - 1) for _ in self.atoms]
            for k, activation in enumerate(maps):
                starts = rng.choice(np.arange(8, 116), size=3, replace=False)
                for start in starts:
                    activation[int(start) + 11] = rng.uniform(0.3, 0.9) * rng.choice([-1.0, 1.0])
            self.signals.append(forward(maps, self.atoms, 128))
            self.true_maps.append(maps)

    def test_dictionary_gradient_matches_finite_difference(self):
        rng = np.random.default_rng(402)
        atoms = [d.copy() for d in self.atoms]
        maps = []
        for _ in self.signals:
            maps.append([rng.normal(size=128 + d.size - 1) for d in atoms])
        grads = dictionary_gradient(self.signals, maps, atoms)
        eps = 1e-6
        for k in range(len(atoms)):
            direction = rng.normal(size=atoms[k].size)
            direction /= np.linalg.norm(direction)
            plus = [d.copy() for d in atoms]
            minus = [d.copy() for d in atoms]
            plus[k] += eps * direction
            minus[k] -= eps * direction
            # The smooth loss accepts unit atoms; use the raw equivalent
            # finite-difference expression directly via explicit convolutions.
            def raw_loss(ds):
                total = 0.0
                for x, a in zip(self.signals, maps):
                    y = np.zeros_like(x)
                    for coeff, atom in zip(a, ds):
                        full = np.convolve(coeff, atom, mode="full")
                        y += full[atom.size - 1:atom.size - 1 + x.size]
                    r = y - x
                    total += 0.5 * np.dot(r, r)
                return total
            numerical = (raw_loss(plus) - raw_loss(minus)) / (2 * eps)
            analytic = float(np.dot(grads[k], direction))
            self.assertAlmostEqual(numerical, analytic, delta=2e-6)

    def test_learning_preserves_unit_norm_and_nonincreasing_objective(self):
        rng = np.random.default_rng(403)
        initial = []
        for d in self.atoms:
            candidate = d + 0.18 * rng.normal(size=d.size)
            candidate /= np.linalg.norm(candidate)
            initial.append(candidate)
        result = learn_convolutional_dictionary(
            self.signals, initial, lam=0.002, outer_iterations=5,
            coding_iterations=100, coding_tolerance=2e-5,
            initial_dictionary_step=0.2, power_iterations=20,
        )
        self.assertEqual(len(result.atoms), 3)
        for atom in result.atoms:
            self.assertAlmostEqual(np.linalg.norm(atom), 1.0, places=9)
        self.assertEqual(len(result.objective_history), result.iterations)
        self.assertTrue(all(np.isfinite(v) for v in result.objective_history))
        self.assertTrue(all(b <= a + 1e-8 for a, b in zip(result.objective_history, result.objective_history[1:])))
        self.assertLess(result.objective_history[-1], result.objective_history[0])

    def test_variable_length_training_signals(self):
        rng = np.random.default_rng(404)
        short = self.signals[0][:96]
        long = np.concatenate([self.signals[1], self.signals[1][:32]])
        initial = [d.copy() for d in self.atoms]
        result = learn_convolutional_dictionary(
            [short, long], initial, lam=0.003, outer_iterations=2,
            coding_iterations=40, initial_dictionary_step=0.1,
            power_iterations=12,
        )
        self.assertEqual(len(result.coefficients), 2)
        self.assertEqual(result.coefficients[0][0].size, short.size + initial[0].size - 1)
        self.assertEqual(result.coefficients[1][0].size, long.size + initial[0].size - 1)

    def test_invalid_zero_atom_rejected(self):
        with self.assertRaises(ValueError):
            learn_convolutional_dictionary(self.signals, [np.zeros(12)], outer_iterations=1)


    def test_dictionary_gradient_rejects_non_unit_atoms(self):
        maps = [[np.zeros(128 + d.size - 1) for d in self.atoms] for _ in self.signals]
        invalid = [d.copy() for d in self.atoms]
        invalid[0] *= 2.0
        with self.assertRaises(ValueError):
            dictionary_gradient(self.signals, maps, invalid)

    def test_dictionary_learning_is_deterministic(self):
        rng = np.random.default_rng(405)
        initial = []
        for d in self.atoms:
            candidate = d + 0.1 * rng.normal(size=d.size)
            candidate /= np.linalg.norm(candidate)
            initial.append(candidate)
        kwargs = dict(
            lam=0.002, outer_iterations=3, coding_iterations=35,
            initial_dictionary_step=0.5, power_iterations=10, seed=99,
        )
        first = learn_convolutional_dictionary(self.signals, initial, **kwargs)
        second = learn_convolutional_dictionary(self.signals, initial, **kwargs)
        for a, b in zip(first.atoms, second.atoms):
            np.testing.assert_array_equal(a, b)
        for a, b in zip(first.objective_history, second.objective_history):
            self.assertEqual(a, b)


    def test_outer_learning_does_not_report_convergence_when_inner_fista_is_unfinished(self):
        result = learn_convolutional_dictionary(
            self.signals, self.atoms, lam=0.002, outer_iterations=3,
            coding_iterations=1, coding_tolerance=1e-12,
            dictionary_tolerance=1e6, initial_dictionary_step=0.1,
            power_iterations=8,
        )
        self.assertFalse(all(result.coding_converged))
        self.assertFalse(result.converged)

    def test_non_finite_learning_configuration_rejected(self):
        with self.assertRaises(ValueError):
            learn_convolutional_dictionary(
                self.signals, self.atoms, outer_iterations=1,
                initial_dictionary_step=float("nan"),
            )

    def test_initial_coefficients_fista_warm_start_validation(self):
        from krm_td_csc.solver import solve_cbpdn_fista
        good = [[np.zeros(128 + 11) for _ in self.atoms] for _ in self.signals]
        result = solve_cbpdn_fista(self.signals[0], self.atoms, lam=0.003, max_iterations=10, initial_coefficients=good[0])
        self.assertEqual(len(result.coefficients), len(self.atoms))
        with self.assertRaises(ValueError):
            solve_cbpdn_fista(self.signals[0], self.atoms, initial_coefficients=[np.zeros(3)])


if __name__ == "__main__":
    unittest.main()
