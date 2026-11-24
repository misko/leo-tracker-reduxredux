from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_design_template import Designs, build
from grid_feature_projection import exact
from tools.pipeline_eval.variants.algo08_curved_design import direct_features


def original(problem, frequency, derivative, modes, scales, geometry_only):
    use_direct = geometry_only
    result = (direct_features(problem, derivative, modes, scales) if use_direct else None)
    return result


@pytest.fixture
def designs(tmp_path):
    library = tmp_path / "template.so"
    build(library)
    return Designs(library)


def inputs():
    rows = 13
    random = np.random.default_rng(37)
    view = SimpleNamespace(variant="radio_noise", hardware=random.normal(size=(rows, 9)),
                           smooth=random.normal(size=(rows, 6)), constants=random.normal(size=(rows, 5)),
                           labels=[4, 9, 13], supported=[4, 13], supported_local=[0, 2],
                           flat_labels=np.arange(rows) % 3, q=random.uniform(.85, 1.15, rows),
                           phase_sigma=np.array([1., 3., 5.]))
    return view, np.zeros(rows), random.normal(size=rows), random.normal(size=(rows, 3)), np.ones(3)


def test_exact_signed_values_and_private_layout_across_fresh_locations(designs):
    args = inputs()
    namespace = {"_assemble": original}
    with designs.binding(namespace):
        first = namespace["_assemble"](*args, True)
        for i in range(4):
            changed = (*args[:2], args[2] * -i, -args[3], args[4])
            matrix = namespace["_assemble"](*changed, True)
            assert exact(matrix, original(*changed, True))
            assert not np.shares_memory(first, matrix)
    assert designs.counts["assembly_calls"] == 5
    assert designs.counts["assembly_exact_checks"] == 1
    assert namespace["_assemble"] is original


def test_changed_static_operand_or_nonunit_model_uses_original(designs):
    args = inputs()
    namespace = {"_assemble": original}
    with designs.binding(namespace):
        namespace["_assemble"](*args, True)
        args[0].phase_sigma = np.array([2., 4., 9.])
        assert exact(namespace["_assemble"](*args, True), original(*args, True))
        nonunit = (*args[:4], np.array([1., 2., 1.]))
        assert exact(namespace["_assemble"](*nonunit, True), original(*nonunit, True))
    assert designs.counts["assembly_view_fallbacks"] == designs.counts["assembly_layout_fallbacks"] == 1
