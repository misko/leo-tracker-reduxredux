from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.sequential_fix_omitted import east_offer
from tools.pipeline_eval.qualification.sequential_fix_timing import queue, timing
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants.sequential_fix import release


def forecast(checkpoint, *, visits, latlon=(37.90, -122.54), refreshed=False):
    support = dict(
        nominal_radius95_km=0.40,
        information_condition=5.0,
        east_north_km=[0.0, 0.0],
        active_points=120,
        latest_by_norad={str(i): 219.0 if refreshed and i < 3 else 190.0 for i in range(1, 5)},
    )
    return dict(
        id="capture",
        checkpoint=checkpoint,
        tile={"width_km": 25.0},
        catalog_sha256="fixed",
        support=dict(first_visit=0, last_visit=visits - 1),
        result=dict(
            status="ok",
            arms={arm: dict(latlon=list(latlon)) for arm in ARMS},
            metrics=dict(terminal_support={arm: deepcopy(support) for arm in ARMS}),
        ),
    )


def test_pair_requires_new_accepted_orbital_support_in_both_arms():
    first = forecast(210, visits=100)
    update = forecast(255, visits=130, latlon=(37.901, -122.54), refreshed=True)
    assert release(first, update)["released"]
    update["result"]["metrics"]["terminal_support"]["fitted_c"]["latest_by_norad"]["2"] = 210.0
    decision = release(first, update)
    assert not decision["released"]
    assert decision["arms"]["c0"]["reasons"] == []
    assert decision["arms"]["fitted_c"]["reasons"] == ["refreshed_orbits"]


def test_gate_rejects_face_constraint_and_unmatched_input():
    first = forecast(210, visits=100)
    update = forecast(255, visits=130, refreshed=True)
    update["result"]["metrics"]["terminal_support"]["c0"]["east_north_km"] = [12.10, 0.0]
    assert release(first, update)["arms"]["c0"]["reasons"] == ["tile_face"]
    update["catalog_sha256"] = "later"
    with pytest.raises(ValueError, match="causal catalogue"):
        release(first, update)


def checkpoint(available, visits, wall):
    return dict(
        service=dict(service_wall_s=wall, systemd=dict(CPUUsageNSec=str(int(wall * 1e9)))),
        support=dict(available_s=[available, available], scheduled=visits, invalid=0),
        input_preparation_wall_s=0.0,
    )


def test_eager_counts_already_dispatched_raw_work_and_barrier_holds_the_tail():
    raw = [
        dict(visit=i, arrival_s=t, raw_cpu_s=1.0, raw_wall_s=1.0, valid=True)
        for i, t in enumerate((209, 254, 265, 299))
    ]
    rows = [checkpoint(210, 1, 5), checkpoint(255, 2, 20), checkpoint(300, 4, 40)]
    eager = timing(rows, True, raw)["scenarios"][0]
    assert eager["model_255_finish_s"] == 275
    assert eager["valid_visits_saved_eager"] == 1
    assert eager["raw_cpu_saved_barrier_s"] == 2
    assert eager["total_cpu_saved_eager_s"] == 16
    assert queue(raw, 1, hold_from=2, resume_s=280)[2] == (280, 281)

    rows[1] = checkpoint(255, 2, 55)
    eager = timing(rows, True, raw)["scenarios"][0]
    assert eager["raw_cpu_saved_eager_s"] == 0
    refusal = timing(rows, False, raw)["scenarios"][0]
    assert refusal["raw_cpu_saved_barrier_s"] == 0
    assert refusal["model_barrier_policy_finish_s"] == 352
    assert refusal["total_cpu_saved_eager_s"] == -60


def test_omitted_offer_has_five_kilometers_between_the_tile_faces():
    tile, gap = east_offer(dict(center=[37.906, -122.545]))
    assert tile["width_km"] == 25.0
    assert tile["center"][0] == 37.906
    assert tile["center"][1] > -122.545
    assert gap == pytest.approx(5.0)
