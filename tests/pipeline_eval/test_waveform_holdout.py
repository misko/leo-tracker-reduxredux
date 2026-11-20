"""Component checks for the blinded stressed waveform study."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import waveform_holdout_model as model
from tools.pipeline_eval.qualification import waveform_holdout_results as scores
from tools.pipeline_eval.qualification import waveform_holdout_trial as trial


def test_truth_catalogue_excludes_unchanged_and_unknown_orbit_identities():
    def elements(norad, **changes):
        return SimpleNamespace(satnum=norad, **({field: 1.0 for field in model.ELEMENTS} | changes))

    revised = [elements(1), elements(2, ecco=0.005), elements(3, nodeo=0.1)]
    causal = [elements(1), elements(2), elements(4)]
    assert [sat.satnum for sat in model.changed_bank(revised, causal)] == [2]


def test_interferer_is_finite_qpsk_with_cyclic_prefix_and_local_to_burst():
    start, stop = 1000, 5000
    burst = dict(
        seed=42, start=start, stop=stop, frequency_hz=0.0, level=700.0, lane_gains=[1.0, 0.8]
    )
    wave = model.interference(burst)
    np.testing.assert_array_equal(wave[: model.CP], wave[model.FFT : model.FFT + model.CP])
    spectrum = np.fft.fft(wave[model.CP : model.FFT + model.CP])
    assert np.count_nonzero(np.abs(spectrum) > 5) == model.OCCUPIED
    assert np.sqrt(np.mean(np.abs(wave) ** 2)) == pytest.approx(700.0, abs=10.0)
    row = dict(sample_seed=11, tone_hz=74_000, tone_amplitude=150, planted=[None, None])
    profile = dict(sample_rate_truth_hz=model.RATE)
    frame = model.pulse_bank()["lower"]
    clean = model.iq(dict(row, burst=None), profile, frame)
    busy = model.iq(dict(row, burst=burst), profile, frame)
    assert busy.shape == (200_000, 2, 2) and busy.dtype == np.dtype("<i2")
    np.testing.assert_array_equal(clean[:start], busy[:start])
    np.testing.assert_array_equal(clean[stop:], busy[stop:])
    assert np.count_nonzero(busy[start:stop] != clean[start:stop]) > 10_000


def test_scheduled_gaps_are_common_to_both_receivers_and_fades_keep_distinct_labels():
    rows = [
        dict(planted=[dict(norad=i, amplitude=1000) for _ in range(2)])
        for i in (1, 2)
        for _ in range(22)
    ]
    model.stress(rows, np.random.default_rng(33))
    assert sum(r["activity_gap"] for r in rows) == 4
    for i in (1, 2):
        gaps = [j for j, r in enumerate(rows) if r.get("planned_norad") == i]
        assert len(gaps) == 2 and gaps[1] == gaps[0] + 1
    faded = [v for v in rows if v["fade_amplitude"] != 1]
    assert faded
    for r in faded:
        assert r["planted"][0] == r["planted"][1]
        assert r["planted"][0]["amplitude"] == pytest.approx(1000 * r["fade_amplitude"])


def test_matched_inputs_both_arms_and_false_publishing_outside_region():
    truth = [10, 77]
    offers = {
        "containing": truth,
        "omitted": [10 + 14 / 111, 77],
        "far-omitted": [10 - 55 / 111, 77],
    }
    requests, predictions, conditions = [], [], {}
    for j, (name, center) in enumerate(offers.items()):
        ident = str(j)
        conditions[ident] = name
        req = dict(
            id=ident,
            tile=center,
            screen_center=center,
            native_sha256="a" * 64,
            catalog_sha256="b" * 64,
        )
        requests.append(req)
        for method in trial.METHODS:
            result = dict(
                status="ok",
                boundary="test",
                metrics={},
                arms={arm: dict(latlon=center, rf_rms_hz=1.0) for arm in scores.ARMS},
            )
            predictions.append(
                dict(
                    id=ident,
                    method=method,
                    result=result,
                    input_sha256=trial.stock.raw_digest(encoded(req)),
                    native_sha256=req["native_sha256"],
                    catalogue_sha256=req["catalog_sha256"],
                    verified_limits=scores.LIMIT,
                )
            )
    joined = scores.bind_predictions(predictions, requests, trial.METHODS)
    rows, _ = scores.region_scores(
        joined, requests, dict(coordinate=truth, conditions=conditions, offers=offers)
    )
    assert len(rows) == 12 and sum(r["false_publication"] for r in rows) == 8
    predictions[1]["catalogue_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="same scientific request"):
        scores.bind_predictions(predictions, requests, trial.METHODS)
