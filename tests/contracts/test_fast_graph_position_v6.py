"""ALGO07 publication requires full matched physical and predictive evidence."""

import copy
import hashlib
import json
import math

import pytest
from test_fast_graph_position_v5 import terminal as previous_terminal

from leo.contracts.fast_graph_position import ARMS, KIND
from leo.contracts.fast_graph_position_v6 import (
    MODEL_VERSION,
    POLICY,
    incumbent_owners,
    owners,
    validate_terminal,
)


def fit(ownership, native, *, objective, reassigned=()):
    return dict(
        status="complete",
        qualified=True,
        all_gates_pass=True,
        phase_closed=True,
        optimizer_success=True,
        mixture_phase_interior=True,
        mixture_gates_pass=True,
        objective=objective,
        lost_ids=[],
        unexpected_reassigned_ids=[],
        history=[dict(success=True, phase_change_s=0.001)],
        exact=[dict(all_pass=True)],
        phase_boundary_masses=[0.001],
        endpoint_latlon=[37.9, -122.5],
        tracks=[dict(component="native", norad=ownership[native[0]], observation_ids=native)],
        native_ids_sha256=hashlib.sha256("\n".join(sorted(native)).encode()).hexdigest(),
        proposed_owners=dict(ownership),
        reassigned_ids=list(reassigned),
        owners_sha256=hashlib.sha256(json.dumps(ownership, sort_keys=True).encode()).hexdigest(),
    )


def terminal():
    old = previous_terminal()
    prior = incumbent_owners(old)
    target = sorted(oid for oid, n in prior["fitted_c"].items() if n == 999)
    new = 1000
    penalty = 2 * math.log(2)
    controls = {a: fit(dict(v), target, objective=100.0) for a, v in prior.items()}
    proposed = {
        a: {oid: new if oid in target else n for oid, n in v.items()} for a, v in prior.items()
    }
    pair = {a: fit(v, target, objective=90.0, reassigned=target) for a, v in proposed.items()}
    record = dict(
        name="999_to_1000",
        target=999,
        accepted=True,
        hypothesis=dict(
            name="999_to_1000",
            norad=new,
            mapping={"native": new},
            allowed_families=[999, new],
            penalty=penalty,
            predictive={a: dict(gains=[1.0] * 5, mean=1.0, wins=5, pass_check=True) for a in ARMS},
        ),
        pair=pair,
        control=controls,
        bounds=dict.fromkeys(ARMS, 100.0),
        matched_published_objectives=dict.fromkeys(ARMS, 101.0),
        gains=dict.fromkeys(ARMS, 10.0 - penalty),
    )
    guard = dict(
        candidates=[999, new],
        proposed=new,
        passed=True,
        status="passed",
        model="receiver_offset",
        phase_sd_s=5.0,
        minimum_unique_folds=5,
        required_minimum_margin_exclusive=0.0,
        missing=[],
        unique_folds=5,
        total_partitions=5,
        retained_fold_ids=list(range(5)),
        minimum_margin=1.0,
        competitors=[
            dict(
                arm=a,
                norad=999,
                margins=[1.0] * 5,
                folds=5,
                wins=5,
                minimum_margin=1.0,
                mean_margin=1.0,
            )
            for a in ARMS
        ],
    )
    candidate = dict(
        policy=POLICY,
        old_norad=999,
        new_norad=new,
        target_ids=target,
        observation_ids=sorted(set().union(*(set(v) for v in prior.values()))),
        published_owners=proposed,
        arms={a: dict(endpoint_latlon=r["endpoint_latlon"]) for a, r in pair.items()},
        record=record,
        guard=guard,
        shortlist_count=2,
        cutoff_utc_ns=200_000_000_000,
        element=dict(element_epoch_utc_ns=100_000_000_000, collected_utc_ns=100_000_000_000),
        baseline_objectives=dict.fromkeys(ARMS, 102.0),
    )
    return dict(
        schema_version=6,
        kind=KIND,
        model_version=MODEL_VERSION,
        input_sha256=old["input_sha256"],
        state="complete",
        session_id=old["session_id"],
        incumbent=old,
        decision="ALGO07_reassociation",
        candidate=candidate,
        reference_usage="none",
        future_TLE_used=False,
        matched_c_inputs=True,
        selected_arm="fitted_c",
        recovery_policy=POLICY,
        incumbent_seconds=old["total_seconds"],
        recovery_seconds=1.0,
        total_seconds=old["total_seconds"] + 1.0,
        position=dict(latitude_deg=37.9, longitude_deg=-122.5),
        read_audit=dict(verified=True),
    )


def validate(doc):
    return validate_terminal(doc, input_sha256=doc["input_sha256"])


def test_guarded_reassociation_preserves_exact_incumbent_and_all_baseline_ids():
    doc = terminal()
    assert validate(doc) is doc
    assert doc["incumbent"] == previous_terminal()
    assert owners(doc) == doc["candidate"]["published_owners"]
    assert incumbent_owners(doc["incumbent"])["fitted_c"]["new-0"] == 999


def test_algo06_fallback_retains_published_algo05_gap_owners():
    old = previous_terminal()
    old.update(decision="ALGO05_fallback", candidate=None)
    expected = old["incumbent"]["candidate"]["trial"]["arms"]
    assert incumbent_owners(old) == {a: r["proposed_owners"] for a, r in expected.items()}
    assert incumbent_owners(old)["fitted_c"]["gap-0"] == 100


@pytest.mark.parametrize(
    "failure",
    [
        "gps",
        "future",
        "age",
        "position",
        "runtime",
        "read",
        "same_identity",
        "owned_destination",
        "drop",
        "add",
        "other_change",
        "partial_arms",
        "optimizer",
        "phase",
        "nan_phase",
        "boundary",
        "native_hash",
        "native_duplicate",
        "control_hash",
        "owners_hash",
        "exact",
        "unqualified_control",
        "negative_gain",
        "wrong_bound",
        "nonfinite_baseline_bound",
        "nonfinite_matched_bound",
        "raw_track_owner",
        "contradictory_exact",
        "penalty",
        "inherited_wins",
        "inherited_mean",
        "guard_missing",
        "guard_competitor",
        "guard_margin",
        "guard_fold_count",
        "guard_summary",
        "unknown_native",
        "selected_arm",
        "reassigned_ids",
    ],
)
def test_rejects_inconsistent_scientific_evidence(failure):
    d = terminal()
    c = d["candidate"]
    row = c["record"]["pair"]["c0"]
    if failure == "gps":
        d["reference_usage"] = "GPS"
    elif failure == "future":
        c["element"]["collected_utc_ns"] = c["cutoff_utc_ns"] + 1
    elif failure == "age":
        c["cutoff_utc_ns"] += 73 * 3600 * 10**9
    elif failure == "position":
        d["position"]["latitude_deg"] = 0
    elif failure == "runtime":
        d["recovery_seconds"] = 1201
    elif failure == "read":
        d["read_audit"]["verified"] = False
    elif failure == "same_identity":
        c["new_norad"] = c["old_norad"]
    elif failure == "owned_destination":
        c["new_norad"] = next(
            n for n in incumbent_owners(d["incumbent"])["c0"].values() if n != 999
        )
    elif failure == "drop":
        c["published_owners"]["c0"].pop("new-0")
    elif failure == "add":
        c["published_owners"]["c0"]["unrelated"] = 1000
    elif failure == "other_change":
        c["published_owners"]["c0"]["new-0"] = 1001
    elif failure == "partial_arms":
        c["record"]["pair"].pop("c0")
    elif failure == "optimizer":
        row["optimizer_success"] = False
    elif failure == "phase":
        row["history"][-1]["phase_change_s"] = 0.011
    elif failure == "nan_phase":
        row["history"][-1]["phase_change_s"] = float("nan")
    elif failure == "boundary":
        row["phase_boundary_masses"] = [0.01]
    elif failure == "native_hash":
        row["native_ids_sha256"] = "different"
    elif failure == "native_duplicate":
        row["tracks"][0]["observation_ids"].append("new-0")
    elif failure == "control_hash":
        c["record"]["control"]["c0"]["native_ids_sha256"] = "different"
    elif failure == "owners_hash":
        row["owners_sha256"] = "different"
    elif failure == "exact":
        row["exact"] = []
    elif failure == "unqualified_control":
        c["record"]["control"]["c0"]["qualified"] = False
    elif failure == "negative_gain":
        c["record"]["gains"]["c0"] = -1
    elif failure == "wrong_bound":
        c["record"]["bounds"]["c0"] = 102.0
    elif failure == "nonfinite_baseline_bound":
        c["baseline_objectives"]["c0"] = float("nan")
    elif failure == "nonfinite_matched_bound":
        c["record"]["matched_published_objectives"]["c0"] = float("nan")
    elif failure == "raw_track_owner":
        row["tracks"][0]["norad"] = 999
    elif failure == "contradictory_exact":
        row["exact"][0]["failed"] = {"residual": -1}
    elif failure == "penalty":
        c["record"]["hypothesis"]["penalty"] = 0.0
    elif failure == "inherited_wins":
        c["record"]["hypothesis"]["predictive"]["c0"]["wins"] = 3
    elif failure == "inherited_mean":
        c["record"]["hypothesis"]["predictive"]["c0"]["mean"] = 2.0
    elif failure == "guard_missing":
        c["guard"]["missing"] = [1]
    elif failure == "guard_competitor":
        c["guard"]["competitors"].pop()
    elif failure == "guard_margin":
        c["guard"]["competitors"][0]["margins"][0] = 0.0
    elif failure == "guard_fold_count":
        c["guard"]["unique_folds"] = 4
    elif failure == "guard_summary":
        c["guard"]["minimum_margin"] = 2.0
    elif failure == "unknown_native":
        c["observation_ids"].remove("new-0")
    elif failure == "selected_arm":
        c["arms"]["c0"]["endpoint_latlon"] = [0.0, 0.0]
    elif failure == "reassigned_ids":
        row["reassigned_ids"] = []
    with pytest.raises(ValueError):
        validate(d)


def test_exact_fallback_and_immutable_v5_incumbent():
    d = terminal()
    old = copy.deepcopy(d["incumbent"])
    d.update(decision="ALGO06_fallback", candidate=None, position=copy.deepcopy(old["position"]))
    assert validate(d) is d and d["incumbent"] == old
    assert owners(d) == incumbent_owners(old)
    d["position"]["latitude_deg"] = 0
    with pytest.raises(ValueError):
        validate(d)


def test_no_predictive_family_mass_and_five_feasible_partitions_are_valid():
    d = terminal()
    for role in ("pair", "control"):
        for row in d["candidate"]["record"][role].values():
            row["phase_boundary_masses"] = []
    assert validate(d) is d


def test_incidental_raw_additions_are_projected_out_of_published_owners():
    d = terminal()
    for row in d["candidate"]["record"]["pair"].values():
        row["proposed_owners"]["incidental"] = 1234
        row["added_ids"] = ["incidental"]
        row["owners_sha256"] = hashlib.sha256(
            json.dumps(row["proposed_owners"], sort_keys=True).encode()
        ).hexdigest()
    assert validate(d) is d


@pytest.mark.parametrize("complete", [True, False])
def test_reassociation_mapping_covers_every_native_track_in_the_family(complete):
    d = terminal()
    record = d["candidate"]["record"]
    for role in ("pair", "control"):
        for row in record[role].values():
            track = row["tracks"][0]
            ids = track["observation_ids"]
            row["tracks"] = [
                dict(track, observation_ids=ids[:10]),
                dict(track, component="second", observation_ids=ids[10:]),
            ]
    if complete:
        record["hypothesis"]["mapping"]["second"] = 1000
        assert validate(d) is d
    else:
        with pytest.raises(ValueError, match="complete native satellite family"):
            validate(d)
