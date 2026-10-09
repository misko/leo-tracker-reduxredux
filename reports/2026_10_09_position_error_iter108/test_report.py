import copy
import runpy
from pathlib import Path

import pytest

summarize = runpy.run_path(str(Path(__file__).with_name("report.py")))["summarize"]


def fixture():
    member = dict(inventory_label="DS16-001", dataset="DS16")
    population = dict(
        rows=4,
        entropy_nats=dict(mean=2),
        maximum_probability=dict(mean=0.7),
        confidence_below_half=1,
        confidence_half_to_nine_tenths=1,
        confidence_at_least_nine_tenths=2,
    )
    ambiguity = dict(
        populations={name: copy.deepcopy(population) for name in ("all", "linked", "independent")},
        switches=dict(
            links=1, changed=1, confident_satellite_switches=0, weak_or_clutter_switches=1
        ),
    )
    for name in ("linked", "independent"):
        ambiguity["populations"][name].update(
            rows=2,
            confidence_below_half=0,
            confidence_half_to_nine_tenths=1,
            confidence_at_least_nine_tenths=1,
        )
    receipt = dict(
        member=member,
        protocol_sha256="hash",
        status="complete",
        elapsed_s=3,
        arms={
            a: dict(
                ambiguity=copy.deepcopy(ambiguity),
                objective_delta=-0.1,
                rho0_whole_score_delta=0.2,
                rho0_prediction_gradient_max_abs=0.01,
            )
            for a in ("fitted-c", "zero-c")
        },
    )
    return dict(members=[dict(member=member)]), {"DS16-001": receipt}


def test_matched_descriptive_known_values():
    plan, receipts = fixture()
    result = summarize(plan, receipts, "hash")
    assert result["complete"]
    data = result["metrics"]["DS16"]
    assert data["fitted-c"] == data["zero-c"]
    assert data["zero-c"]["linked_fraction"] == 0.5
    assert data["zero-c"]["mean_entropy_nats"] == 2
    assert data["zero-c"]["confidence_fractions"]["confidence_below_half"] == 0.25


@pytest.mark.parametrize("status", ["missing", "failed"])
def test_incomplete_withholds_all_metrics(status):
    plan, receipts = fixture()
    if status == "missing":
        receipts.clear()
    else:
        receipts["DS16-001"].update(status="failed", error="synthetic failure")
    result = summarize(plan, receipts, "hash")
    assert result["metrics"] is None
    assert result["membership"][0]["status"] == status


def test_provenance_and_matched_arms_required():
    plan, receipts = fixture()
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "wrong hash")
    del receipts["DS16-001"]["arms"]["zero-c"]
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "hash")


def test_empty_linked_population_is_null_not_zero():
    plan, receipts = fixture()
    for arm in receipts["DS16-001"]["arms"].values():
        linked = arm["ambiguity"]["populations"]["linked"]
        linked.update(
            rows=0,
            entropy_nats=dict(mean=None),
            maximum_probability=dict(mean=None),
            **{
                k: 0
                for k in (
                    "confidence_below_half",
                    "confidence_half_to_nine_tenths",
                    "confidence_at_least_nine_tenths",
                )
            },
        )
        arm["ambiguity"]["populations"]["independent"] = copy.deepcopy(
            arm["ambiguity"]["populations"]["all"]
        )
    result = summarize(plan, receipts, "hash")
    linked = result["pooled"]["fitted-c"]["populations"]["linked"]
    assert linked["rows"] == 0 and linked["mean_entropy_nats"] is None
    assert all(v is None for v in linked["confidence_fractions"].values())
    assert result["pooled"]["fitted-c"]["linked_fraction_per_recording"]["min"] == 0


def test_weighting_pooled_coverage_parity_and_runtime():
    plan, receipts = fixture()
    second = copy.deepcopy(receipts["DS16-001"])
    second["member"] = dict(inventory_label="DS17-001", dataset="DS17")
    second["elapsed_s"] = 7
    for arm in second["arms"].values():
        for population in arm["ambiguity"]["populations"].values():
            population["rows"] *= 3
            for k in (
                "confidence_below_half",
                "confidence_half_to_nine_tenths",
                "confidence_at_least_nine_tenths",
            ):
                population[k] *= 3
            population["entropy_nats"]["mean"] = 4
        arm["objective_delta"] = -0.3
    plan["members"].append(dict(member=second["member"]))
    receipts["DS17-001"] = second
    result = summarize(plan, receipts, "hash")
    data = result["pooled"]["zero-c"]
    assert data["mean_entropy_nats"] == 3.5
    assert data["populations"]["linked"]["mean_entropy_nats"] == 3.5
    assert data["max_abs_objective_delta"] == 0.3
    assert result["runtime"]["sum_recording_elapsed_s"] == 10
    assert result["runtime"]["wall_time_s"] is None
