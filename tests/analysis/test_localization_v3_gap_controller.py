from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import gap_controller as gap


def fixture(monkeypatch):
    ids = [f"new-{i}" for i in range(12)]
    parent = ids + ["tail"]
    observations = [dict(observation_id=o) for o in ["old", *parent]]
    protected = {a: {"old": 10} for a in gap.ARMS}
    identity = dict(status="conditionally_supported_identity", norad=20, minimum_margin=50.0)
    annotations = {
        "parent": dict(
            result=dict(track_id="parent", annotation=identity),
            protocol=dict(target=dict(observation_ids=parent)),
        )
    }
    decision = dict(attempts=[dict(track_id="parent", shared_family=True, status="RF_rejected")])
    source = dict(
        protocol=dict(parent_observation_ids=parent),
        branches=[dict(branch_id="branch", observation_ids=ids)],
    )
    trial = dict(
        target_0=dict(
            paired_valid=True,
            target_entries=[dict(observation_ids=ids)],
            arms={
                a: dict(
                    proposed_owners={"old": 10, **dict.fromkeys(ids, 20)},
                    proposed_associated_ids=["old", *ids],
                    final_phase_change_s=0.001,
                    endpoint_latlon=[37.0, -122.0],
                    target_diagnostics=[dict(times_s=list(range(12)))],
                )
                for a in gap.ARMS
            },
        )
    )
    audit = dict(
        all_verified=True,
        rows=[
            dict(
                role=role,
                arm=a,
                verified=True,
                exact_family_replays=[dict(all_gate_slacks=dict(rms=2.0))],
                phase_reference_check=dict(phase_change_s=0.001),
                incumbent_ownership_changes=[],
            )
            for role in ("control", "target_0")
            for a in gap.ARMS
        ],
    )
    monkeypatch.setattr(gap, "prepare_gap", lambda *a: source)
    monkeypatch.setattr(
        gap,
        "annotate_gap",
        lambda *a: (dict(result=dict(annotation=identity)), dict(stage="annotation")),
    )
    monkeypatch.setattr(gap, "fit_gap", lambda *a: (trial, dict(stage="fit")))
    monkeypatch.setattr(gap, "audit_gap", lambda *a: (audit, dict(stage="audit")))
    return observations, protected, annotations, decision, source, trial, audit


def run(data, **kwargs):
    observations, protected, annotations, decision, *_ = data
    return gap.recover_gaps(
        {},
        {},
        observations,
        decision,
        annotations,
        protected,
        run_stage=kwargs.pop("run_stage", lambda name, op, cap: (True, op())),
        clock=kwargs.pop("clock", lambda: 0.0),
        **kwargs,
    )


def test_original_stage_order_caps_and_paired_publication_proof(monkeypatch):
    data = fixture(monkeypatch)
    result = run(data)
    assert result["selected"]["branch_id"] == "branch"
    assert result["selected"]["qualification"]["added_points"] == dict(c0=12, fitted_c=12)
    assert [s["name"] for s in result["stages"]] == [
        "gap-0-prepare",
        "gap-0-branch-annotation",
        "gap-0-branch-inclusion",
        "gap-0-branch-audit",
    ]
    assert [s["timeout_s"] for s in result["stages"]] == [180, 240, 240, 180]
    assert result["candidate"] == gap.compact(
        data[5]["target_0"],
        data[6],
        data[2]["parent"]["result"]["annotation"],
        {o["observation_id"] for o in data[0]},
        data[4]["protocol"]["parent_observation_ids"],
    )
    assert len(result["numerical_receipts"]) == 3


@pytest.mark.parametrize(
    "excluded",
    [
        "not_shared",
        "not_rejected",
        "no_annotation",
        "ambiguous",
        "bundle",
        "inactive",
        "native",
        "gap",
        "owned_c0",
        "owned_fitted_c",
    ],
)
def test_ineligible_parent_never_runs_scientific_stages(monkeypatch, excluded):
    data = fixture(monkeypatch)
    _, owners, annotations, decision, *_ = data
    r = annotations["parent"]["result"]
    if excluded == "not_shared":
        decision["attempts"][0]["shared_family"] = False
    elif excluded == "not_rejected":
        decision["attempts"][0]["status"] = "qualified_candidate"
    elif excluded == "no_annotation":
        annotations.clear()
    elif excluded == "ambiguous":
        r["annotation"]["status"] = "ambiguous_identity"
    elif excluded in ("bundle", "inactive"):
        r["graph_bundle" if excluded == "bundle" else "inactive_graph_fragment"] = True
    elif excluded == "native":
        annotations["parent"]["protocol"]["target"]["native_branch_source"] = "sealed source"
    elif excluded == "gap":
        annotations["parent"]["gap_source"] = {}
    else:
        owners[excluded.removeprefix("owned_")]["new-0"] = 20
    result = run(data, run_stage=lambda *a: pytest.fail("ineligible target evaluated"))
    assert result["candidate"] is None and result["targets"] == []


def test_full_parent_is_not_a_gap_fragment(monkeypatch):
    data = fixture(monkeypatch)
    data[4]["branches"][0]["observation_ids"] = data[4]["protocol"]["parent_observation_ids"]
    result = run(data)
    assert [s["name"] for s in result["stages"]] == ["gap-0-prepare"]
    assert result["candidate"] is None


@pytest.mark.parametrize("stage", ["prepare", "annotation", "inclusion", "audit"])
def test_failed_stage_cannot_supply_a_completed_candidate(monkeypatch, stage):
    data = fixture(monkeypatch)
    result = run(
        data,
        run_stage=lambda name, op, cap: (False, None) if name.endswith(stage) else (True, op()),
    )
    assert result["candidate"] is None and result["trials"] == []
    assert result["stages"][-1]["status"] == "failed"


@pytest.mark.parametrize(
    "failure", ["paired", "audit", "lost_owner", "changed_owner", "different_additions", "phase"]
)
def test_independent_qualification_preserves_published_owners_in_both_arms(monkeypatch, failure):
    data = fixture(monkeypatch)
    trial, audit = data[5]["target_0"], data[6]
    arm = trial["arms"]["fitted_c"]
    if failure == "paired":
        trial["paired_valid"] = False
    elif failure == "audit":
        audit["all_verified"] = False
    elif failure == "lost_owner":
        arm["proposed_owners"].pop("old")
    elif failure == "changed_owner":
        arm["proposed_owners"]["old"] = 999
    elif failure == "different_additions":
        arm["proposed_owners"]["new-0"] = 999
    else:
        arm["final_phase_change_s"] = 0.02
    result = run(data)
    assert result["candidate"] is None
    assert not result["trials"][0]["qualification"]["qualified"]


def test_admission_reserves_twenty_seconds_and_floors_remaining_time(monkeypatch):
    data = fixture(monkeypatch)
    now = [0.0]

    def stage(name, operation, cap):
        now[0] += 1.1
        return True, operation()

    result = run(data, run_stage=stage, clock=lambda: now[0], maximum_seconds=25.9)
    assert [s["timeout_s"] for s in result["stages"]] == [5, 4, 3, 2]


def test_budget_expiry_keeps_already_qualified_candidate(monkeypatch):
    data = fixture(monkeypatch)
    data[4]["branches"].append(dict(branch_id="later", observation_ids=["new-0"]))
    after_audit = []

    def clock():
        if after_audit:
            # The completed audit stays within its cap; time expires before the
            # next admission, rather than a stage port accepting an overrun.
            return after_audit.pop(0)
        return 0.0

    def stage(name, operation, cap):
        value = operation()
        if name.endswith("audit"):
            after_audit.extend([1.0, 1180.0])
        return True, value

    result = run(data, run_stage=stage, clock=clock)
    assert result["selected"]["branch_id"] == "branch"
    assert result["excluded"] == [dict(budget_exhausted="conditional gap recovery deadline")]
    assert len(result["stages"]) == 4


def test_selection_prefers_identity_margin_then_points_then_parent_id():
    def row(tid, margin, count, bid="first"):
        return dict(
            track_id=tid,
            branch_id=bid,
            identity=dict(minimum_margin=margin),
            qualification=dict(qualified=True, added_points=dict(fitted_c=count)),
        )

    rows = [row("b", 5, 20), row("a", 5, 20), row("z", 4, 100), row("x", 5, 19)]
    assert gap.select(rows) is rows[1]
    tied = deepcopy(rows[1])
    tied["branch_id"] = "later"
    assert gap.select([rows[1], tied]) is rows[1]
    rows[1]["qualification"]["qualified"] = False
    assert gap.select(rows) is rows[0]


@pytest.mark.parametrize("budget", [0, -1, 1201, float("nan"), True])
def test_invalid_budget_is_rejected(monkeypatch, budget):
    with pytest.raises(ValueError, match="budget"):
        run(fixture(monkeypatch), maximum_seconds=budget)
