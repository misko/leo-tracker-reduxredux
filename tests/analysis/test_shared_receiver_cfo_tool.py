import numpy as np

from tools.research.profile_shared_receiver_cfo import fit


def test_shared_model_recovers_exact_shared_receiver_signal():
    rng = np.random.default_rng(44)
    templates = rng.normal(size=(2, 2, 8, 600)) + 1j * rng.normal(size=(2, 2, 8, 600))
    response = templates.sum(axis=(1, 2)).T
    train = np.repeat([True, False], 300)
    result = fit(
        response, templates, np.arange(600), train, np.zeros((2, 2)), np.zeros((2, 2)), True
    )
    assert result["train_sse"] < 1e-20
    assert sum(r["held_sse"] for r in result["receivers"]) < 1e-20
    residual = np.array(result["residual_cfo_hz"])
    assert abs(np.diff(residual[1] - residual[0])[0]) < 1e-12


def test_shared_fit_cannot_use_held_response_to_choose_parameters():
    rng = np.random.default_rng(45)
    templates = rng.normal(size=(2, 2, 8, 600)) + 1j * rng.normal(size=(2, 2, 8, 600))
    response = templates.sum(axis=(1, 2)).T
    train = np.arange(600) % 2 == 0
    changed = response.copy()
    changed[~train] *= 17j
    args = (templates, np.arange(600), train, np.zeros((2, 2)), np.zeros((2, 2)), True)
    a, b = fit(response, *args), fit(changed, *args)
    assert a["residual_cfo_hz"] == b["residual_cfo_hz"]
    assert a["train_sse"] == b["train_sse"]
    assert a["receivers"][0]["coefficients"] == b["receivers"][0]["coefficients"]
