import numpy as np
from local_header_relations import evaluate, select_pair


def test_inverted_copy_survives_independent_receiver_and_frame_split():
    rng = np.random.default_rng(39)
    discovery = rng.normal(size=(100, 8))
    discovery[:, 0] = 1
    discovery[:, 7] = -discovery[:, 3]
    pair = select_pair(discovery)
    assert (pair["left"], pair["right"]) == (3, 7)
    held = rng.normal(size=(100, 8))
    held[:, 7] = -held[:, 3]
    result = evaluate(held, held + rng.normal(scale=0.05, size=held.shape), pair)
    assert result["rx1"]["oriented_correlation"] > 0.99
    held[:, 7] = rng.normal(size=100)
    assert abs(evaluate(held, held, pair)["rx1"]["oriented_correlation"]) < 0.2


def test_constant_positions_do_not_supply_a_relation():
    assert select_pair(np.ones((100, 8))) is None
