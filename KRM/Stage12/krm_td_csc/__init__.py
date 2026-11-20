"""Time-domain multi-scale convolutional sparse coding research prototype."""
from .dictionary import initialize_dictionary_from_signal
from .solver import SolverResult, solve_cbpdn_fista
from .operators import forward, adjoint, coefficient_lengths
from .admm import ADMMResult, solve_cbpdn_admm
from .learning import (
    DictionaryLearningResult, dictionary_gradient, dictionary_learning_objective,
    dictionary_smooth_loss, learn_convolutional_dictionary,
)

__all__ = [
    "initialize_dictionary_from_signal",
    "SolverResult",
    "solve_cbpdn_fista",
    "forward",
    "adjoint",
    "coefficient_lengths",
    "ADMMResult",
    "solve_cbpdn_admm",
    "DictionaryLearningResult",
    "dictionary_gradient",
    "dictionary_learning_objective",
    "dictionary_smooth_loss",
    "learn_convolutional_dictionary",
]
