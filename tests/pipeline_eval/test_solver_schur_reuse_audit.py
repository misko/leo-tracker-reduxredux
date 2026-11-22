import importlib

import numpy as np


def test_exact_float_residue_reduction_handles_extremes_and_subnormals():
    audit = importlib.import_module("reports.ALGO08.single-core-2x.solver_schur_reuse_audit")
    values = np.array([0., -0., .5, -2.0, np.nextafter(1., 2.), np.finfo(float).max,
                       np.nextafter(0., 1.), -np.finfo(float).tiny])
    rational = [value.as_integer_ratio() for value in values]
    expected = [n * pow(d, -1, audit.PRIME) % audit.PRIME for n, d in rational]
    np.testing.assert_array_equal(audit.residues(values) % audit.PRIME, expected)


def test_exact_rank_and_leading_factor_input_ignore_unused_upper_triangle():
    audit = importlib.import_module("reports.ALGO08.single-core-2x.solver_schur_reuse_audit")
    reference = np.eye(3)
    changed = np.diag([1., np.nextafter(1., 2.), np.nextafter(1., 0.)])
    changed[0, 2] = 9.
    assert audit.unchanged_prefix(reference, changed) == 1
    symmetric = np.tril(changed) + np.tril(changed, k=-1).T
    assert audit.rank_mod(audit.residues(symmetric) - audit.residues(reference)) == 2
