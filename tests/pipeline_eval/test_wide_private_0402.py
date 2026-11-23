from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from wide_private_0402 import compare_bound, topology


def test_topology_distinguishes_private_and_shared_columns_using_real_group_labels():
    groups = np.array([7, 7, 12, 12])
    design = np.array([[1., 2., 0., 6.], [2., 0., 3., 7.], [0., 0., -0., 5.], [0., 0., 0., 2.]])
    assert topology(design, groups) == dict(maximum_private=3, shared=1, gram_slots=17,
                                           per_group_private=[3, 0], reason="private_columns")
    assert topology(design[:, [0, 1, 3]], groups)["reason"] == "other"


def test_bound_compatibility_checks_update_count_and_output_scale():
    stock = dict(negative_twice_elbo=80000., conditional_residual_hz=np.array([-200., 100.]), precision_iterations=13)
    wide = dict(stock, negative_twice_elbo=80000. + 1e-8, conditional_residual_hz=np.array([-200., 100. + 1e-8]))
    diffs, matched = compare_bound(stock, wide)
    assert matched and diffs["conditional_residual_hz"] > 0.
    assert not compare_bound(stock, dict(wide, precision_iterations=14))[1]
    assert not compare_bound(stock, dict(wide, negative_twice_elbo=80000. + 1e-5))[1]
