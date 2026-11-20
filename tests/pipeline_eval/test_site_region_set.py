import numpy as np
import pytest

from leo.sky.frames import greenwich_mean_sidereal_time_rad, julian_day_from_utc_ns
from tests.pipeline_eval.geometry import ANCHOR, tle
from tools.pipeline_eval.qualification import site_region_set_trial as trial
from tools.pipeline_eval.qualification.native_joint_full_results import roi_margin
from tools.pipeline_eval.scoring import distance_km
from tools.pipeline_eval.variants import site_region_set as model


def example_scores(a, b, *, position_ready):
    return [
        dict(
            id=ident,
            latlon=[0, 0],
            held=value,
            held_rms_hz=100.0,
            point=dict(eligible=position_ready),
        )
        for ident, value in zip("abcd", (a, b, 1.0, 2.0), strict=True)
    ]


def test_public_placements_schedule_symmetric_four_offer_pairs():
    origin = (40.15, -88.16)
    orders, nominal_centres = set(), set()
    for i in range(3):
        present, absent = list(trial.panels(origin, "replay", i))
        assert len(present["offers"]) == len(absent["offers"]) == 4
        a, b = (
            {offer["id"]: offer["center"] for offer in panel["offers"]}
            for panel in (present, absent)
        )
        shared = a.keys() & b.keys()
        assert len(shared) == 2
        assert all(a[ident] == b[ident] for ident in shared)
        sums = []
        for centres in (a.values(), b.values()):
            corner_sums = [sum(distance_km(x, y) for y in centres) for x in centres]
            assert max(corner_sums) - min(corner_sums) < 1e-8
            sums.append(corner_sums[0])
        assert sums[0] == pytest.approx(sums[1], abs=1e-8)
        allowed = [offer for offer in present["offers"] if roi_margin(origin, offer) > 0]
        assert len(allowed) == 1
        assert all(roi_margin(origin, offer) < 0 for offer in absent["offers"])
        nominal_centres.add(tuple(allowed[0]["center"]))
        orders.add(present["offers"].index(allowed[0]))
    assert len(nominal_centres) == 3
    assert len(orders) >= 2


def test_site_envelopes_keep_region_rejection_and_point_decisions_distinct():
    fold = model.fold(
        {
            "a": ([0.06, 0.15], [0.14, 0.19]),
            "b": ([0.09, 0.18], [0.13, 0.25]),
        }
    )
    a = model.decide(example_scores(0.06, 0.1, position_ready=False), fold)
    assert (a["region_decision"], a["region"], a["point"], a["p_wrong"]) == (
        "region",
        "a",
        None,
        1 / 3,
    )
    b = model.decide(example_scores(0.21, 0.22, position_ready=True), fold)
    assert (b["region_decision"], b["region"], b["point"], b["p_containing"]) == (
        "none",
        None,
        None,
        1 / 3,
    )
    c = model.decide(example_scores(0.16, 0.20, position_ready=True), fold)
    assert (c["region_decision"], c["region"], c["point"], c["forced"]) == (
        "withheld",
        None,
        None,
        "a",
    )
    for scores in (
        example_scores(0.06, 0.06, position_ready=True),
        example_scores(0.06, 0.061, position_ready=True),
    ):
        d = model.decide(scores, fold)
        assert d["region_decision"] == "withheld"
        assert d["point"] is None
    assert model.fold({"a": ([0.06], [])}) is None


@pytest.fixture(scope="module")
def portugal():
    clock = dict(
        anchor_utc_ns=ANCHOR, cutoff_utc_ns=ANCHOR, catalog_timestamp_ns=ANCHOR, duration_s=900
    )
    passes = ((45, 1.25, 1.5), (55, -1.2, 1.5), (66, -0.9, -1.25), (80, 1.0, -1.25))
    elements = []
    for i, midpoint in enumerate(range(83, 825, 74)):
        inclination, dlat, dlon = passes[i % len(passes)]
        inc = np.deg2rad(inclination)
        lat, lon = np.deg2rad(np.add(trial.SIM_TRUTH, (dlat, dlon)))
        # Place near passes along ascending and descending orbital planes to resolve both axes.
        argument = np.arcsin(np.sin(lat) / np.sin(inc))
        if i // 2 % 2:
            argument = np.pi - argument
        jd, fraction = julian_day_from_utc_ns(ANCHOR + midpoint * 10**9)
        right_ascension = lon + greenwich_mean_sidereal_time_rad(jd, fraction).item()
        node = right_ascension - np.arctan2(np.sin(argument) * np.cos(inc), np.cos(argument))
        motion = 15.55 + i % 3 * 0.08
        phase = np.rad2deg(argument) - motion * 360 * midpoint / 86_400
        elements.append(
            tle(50_000 + i, 5.0, np.rad2deg(node) % 360, phase % 360, inclination, motion)
        )
    catalogue = "".join(elements)
    simulated = trial.simulation(clock, catalogue)
    present, absent = trial.panels(trial.SIM_ORIGIN, "test-sgp4", 0)
    return simulated, catalogue, present["offers"], absent["offers"]


def test_physical_point_gate_accepts_an_independent_simulated_position(portugal):
    observation, catalogue, present, absent = portugal
    calibration = model.fold({"other-site": ([0.15], [0.25])})
    successes = model.solve(observation, catalogue, present)["offers"]
    good = model.decide(successes, calibration)
    assert good["region_decision"] == "region"
    assert roi_margin(trial.SIM_TRUTH, next(o for o in present if o["id"] == good["region"])) > 0
    assert distance_km(good["point"], trial.SIM_TRUTH) < model.POINT_BOUND
    assert all(roi_margin(trial.SIM_TRUTH, o) < 0 for o in absent)
    failures = model.solve(observation, catalogue, absent)["offers"]
    bad = model.decide(failures, calibration)
    assert bad["region_decision"] == "none"
    assert bad["point"] is None


def test_candidate_rejects_label_and_future_catalogue(portugal):
    obs, catalogue, present, _ = portugal
    labelled = dict(obs, site_id="private")
    with pytest.raises(ValueError, match="expected anonymous arcs"):
        model.solve(labelled, catalogue, present)
    late = dict(
        obs, clock=dict(obs["clock"], catalog_timestamp_ns=obs["clock"]["cutoff_utc_ns"] + 1)
    )
    with pytest.raises(ValueError, match="after the observation cutoff"):
        model.solve(late, catalogue, present)


def test_rf_level_perturbation_and_tile_order_preserve_scores(portugal):
    observation, catalogue, present, _ = portugal
    original = model.solve(observation, catalogue, present)["offers"]
    frequency_delta = (trial.RF / 1e9 - 11.5) * trial.C_DELTA
    change = dict(
        observation,
        arcs=[
            dict(arc, frequency=(np.asarray(arc["frequency"]) + frequency_delta).tolist())
            for arc in observation["arcs"]
        ],
    )
    moved = {row["id"]: row for row in model.solve(change, catalogue, present[::-1])["offers"]}
    for row in original:
        other = moved[row["id"]]
        assert row["held"] == pytest.approx(other["held"], abs=1e-9)
        assert row["held_rms_hz"] == pytest.approx(other["held_rms_hz"], abs=1e-8)
        assert distance_km(row["latlon"], other["latlon"]) < 0.001
