import math

from tools.pipeline_eval.variants import scaffold_rescue as method


def track(key, ids=("before", "after")):
    return dict(
        key=key,
        observation_ids=list(ids),
        times=[0.0, 1.0],
        values=[2000.0, 2000.0],
        pieces=[
            dict(
                start_s=0.0,
                end_s=1.0,
                reference_time_s=0.0,
                time_scale_s=1.0,
                coefficients_hz=[2000.0],
            )
        ],
    )


def observation(oid, t, y):
    return dict(observation_id=oid, time_s=t, measured_cfo_hz=y, receiver=1, channel=3)


def test_attachment_preserves_exact_members_and_original_physical_cfo():
    lane = (0, 3, "upper", 11e9)
    donor = observation("pilot", 0.6, 2000.0 - 227272.0 + 140.0)
    prior = [observation("before", 0.0, 2000.0), observation("after", 1.0, 2000.0)]
    prepared = dict(tracks=[track("arm")], observations=prior, curved_indices=[0], graph_points=2)
    result, proof = method.attach(
        prepared, dict.fromkeys(("before", "after"), lane), [(lane, donor)], 227272.0
    )
    assert result["graph_points"] == 3
    assert result["tracks"][0]["observation_ids"] == ["before", "pilot", "after"]
    assert result["tracks"][0]["values"].tolist() == [2000.0, 2140.0, 2000.0]
    assert result["observations"] == [prior[0], donor, prior[1]]
    assert result["tracks"][0]["pieces"] is prepared["tracks"][0]["pieces"]
    assert proof["attachments"][0]["lift"] == 1
    assert method.original_members(prepared["tracks"])["arm"] == [
        ("before", 0.0, 2000.0),
        ("after", 1.0, 2000.0),
    ]


def test_ambiguous_or_unbracketed_or_wrong_lane_has_no_attachment():
    a, b = (0, 3, "upper", 11e9), (0, 3, "lower", 11e9)
    prepared = dict(
        tracks=[track("first"), track("second", ("extra_a", "extra_b"))],
        observations=[],
        curved_indices=[0],
        graph_points=4,
    )
    lanes = dict.fromkeys(("before", "after", "extra_a", "extra_b"), a)
    donors = [
        (a, observation("ambiguous", 0.5, 2000.0)),
        (b, observation("edge", 0.5, 2000.0)),
        (a, observation("not_bracketed", 0.0, 2000.0)),
        (a, observation("cfo", 0.5, 2600.0)),
    ]
    out, proof = method.attach(prepared, lanes, donors, 227272.0)
    assert proof["census"] == dict(ambiguous_tracks=1, no_close_bracket=2, cfo_outside_gate=1)
    assert out == prepared


def test_freeze_fitted_noise_and_extend_only_inherited_margin_law():
    stock = dict(
        constant_radio_sigma_hz=150.0,
        floor_sigma_hz=70.0,
        strength_hz2=300.0,
        per_observation_noise_sigma_hz={"historical": 80.5},
    )
    new = method.extend_noise(stock, [{"observation_id": "new", "fractional_margin": 0.03}])
    assert stock["per_observation_noise_sigma_hz"] == {"historical": 80.5}
    assert new["per_observation_noise_sigma_hz"] == {
        "historical": 80.5,
        "new": math.sqrt(70**2 + 300 / 0.03),
    }
    assert {k: v for k, v in new.items() if k != "per_observation_noise_sigma_hz"} == {
        k: v for k, v in stock.items() if k != "per_observation_noise_sigma_hz"
    }
