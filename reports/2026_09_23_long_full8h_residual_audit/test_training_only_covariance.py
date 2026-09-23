"""Regression test: held residual values cannot enter covariance diagnostics."""

import importlib.util
from pathlib import Path

import numpy as np


def load_audit():
    path = Path(__file__).with_name("audit.py")
    spec = importlib.util.spec_from_file_location("residual_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_held_mutation_cannot_change_covariance():
    audit = load_audit()
    time = np.arange(8, dtype=float)
    training = np.array([True, True, True, True, False, False, False, False])
    first = np.array([0.0, 1.0, 2.0, 3.0, 8.0, 9.0, 10.0, 11.0])
    second = np.array([0.0, 2.0, 4.0, 6.0, -8.0, -9.0, -10.0, -11.0])
    original = audit.pairwise_covariance(
        [
            audit.training_residual_rows(time, first, training),
            audit.training_residual_rows(time, second, training),
        ]
    )
    mutated = audit.pairwise_covariance(
        [
            audit.training_residual_rows(time, first + np.where(training, 0.0, 1e9), training),
            audit.training_residual_rows(time, second - np.where(training, 0.0, 1e9), training),
        ]
    )
    assert original == mutated
