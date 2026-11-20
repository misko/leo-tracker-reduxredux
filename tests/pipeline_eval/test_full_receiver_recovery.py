import gzip
import json

import pytest

from tools.pipeline_eval.qualification import full_receiver_recovery as recovery
from tools.pipeline_eval.scoring import ARMS, ROLES


def point(latlon=None):
    return {"latlon": latlon}


def prediction(ident, method):
    return dict(
        id=ident,
        method=method,
        native_sha256="1" * 64,
        catalog_sha256="2" * 64,
        tile=dict(id="original", center=[30, 40]),
        result=dict(
            status="ok",
            boundary="Complete roof decision",
            metrics={},
            arms={arm: point([30, 40]) for arm in ARMS},
        ),
    )


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("native_sha256", "3" * 64),
        ("catalog_sha256", "3" * 64),
        ("tile", {"id": "original", "center": [31, 41]}),
    ],
)
def test_matching_rejects_changed_native_input_catalogue_or_offer(field, forged):
    method, ident = recovery.CLOCK, "DS26-0004"
    row = prediction(ident, method)
    inputs = {
        ident: dict(
            native={"sha256": row["native_sha256"]},
            catalog={"sha256": row["catalog_sha256"]},
            regions=[row["tile"]],
        ),
    }
    recovery.require_matched({ident: row}, inputs, method)
    with pytest.raises(ValueError, match=field):
        recovery.require_matched({ident: dict(row, **{field: forged})}, inputs, method)


def test_selected_archive_rejects_duplicate_method_case(tmp_path):
    method = recovery.CLOCK
    path = tmp_path / "predictions.jsonl.gz"
    record = prediction("DS26-0004", method)
    with gzip.open(path, "wt") as stream:
        stream.write((json.dumps(record) + "\n") * 2)
    with pytest.raises(ValueError, match="entire bound roster"):
        recovery.selected(path, method)


def test_stage_only_withhold_is_not_a_receiver_decision():
    method, ident = recovery.CLOCK, "DS26-0004"
    row = prediction(ident, method)
    inputs = {
        ident: dict(
            native={"sha256": "1" * 64}, catalog={"sha256": "2" * 64}, regions=[row["tile"]]
        ),
    }
    row["result"].update(
        status="withheld",
        reason="fixture did not invoke position",
        metrics={"position_attempted": False},
        arms={arm: point() for arm in ARMS},
    )
    with pytest.raises(ValueError, match="complete paired decision"):
        recovery.require_matched({ident: row}, inputs, method)


def test_both_arm_gate_is_the_intersection_and_withholds_stay_in_denominator():
    refs = {"A", "B", "C"}
    method = recovery.CASCADE
    chosen = {"A": (0.9, 1.2), "B": (1.2, 1.0), "C": (None, None)}
    rows = []
    for name in (*ROLES, *(m for m, _, _ in recovery.SERIES)):
        for ident in sorted(refs):
            values = chosen[ident] if name == method else (1.0, 1.0)
            for arm, error in zip(ARMS, values, strict=True):
                rows.append(
                    dict(
                        id=ident,
                        method=name,
                        arm=arm,
                        error_km=error,
                        conditional_rms_hz=None,
                        within_v5_10pct=error is not None and error <= 1.10,
                    )
                )
    summary, pairs = recovery.summarize(rows, refs)
    results = [r for r in summary if r["method"] == method]
    assert [(r["fixes"], r["offered"], r["within_1km"]) for r in results] == [(2, 3, 1)] * 2
    assert [r["within_10pct_of_paired_v5"] for r in results] == [1, 1]
    assert [r["within_10pct_both_arms"] for r in results] == [0, 0]
    assert pairs[method]["fixed_both"] == ["A", "B"]
