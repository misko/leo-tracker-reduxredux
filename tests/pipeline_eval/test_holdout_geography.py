import numpy as np

from tools.pipeline_eval.qualification.holdout_geography import DEVELOPMENT_CENTERS, fresh_layout
from tools.pipeline_eval.scoring import distance_km


def test_frozen_seed_reproduces_sites_and_edges_and_respects_site_level_separation():
    orientations = set()
    for seed in range(32):
        layout = fresh_layout(np.random.default_rng(seed))
        assert layout == fresh_layout(np.random.default_rng(seed))
        (first, edge_a), (second, edge_b) = layout
        assert {edge_a, edge_b} == {"lower", "upper"}
        assert first[0] * second[0] < 0
        assert 8 <= abs(first[0]) <= 26 and 34 <= abs(second[0]) <= 54
        assert distance_km(first, second) >= 1600
        assert all(distance_km(new, old) >= 1600 for new in (first, second)
                   for old in DEVELOPMENT_CENTERS)
        orientations.add((first[0] > 0, edge_a))
    assert len(orientations) == 4
