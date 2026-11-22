import json
from copy import deepcopy
from hashlib import sha256
from importlib import import_module

import pytest

trial = import_module("reports.ALGO08.single-core-2x.receiver_fractional_selection_trial")


def test_named_prefixes_are_bound_before_opening_recordings(tmp_path, monkeypatch):
    dense = tmp_path / "DS30-0008.json"
    dense.write_text(json.dumps(dict(case=dict(id="DS30-0008", recording=dict(segments=[
        dict(path="dense/first/manifest.json", sha256="a" * 64),
        dict(path="dense/second/manifest.json", sha256="b" * 64),
    ])))))
    pin = sha256(dense.read_bytes()).hexdigest()
    monkeypatch.setitem(trial.PHYSICAL_BINDINGS, "DS30-0008", pin)
    physical = trial.prefix_plan("DS30-0008", dense, tmp_path)
    assert physical.edge == "lower"
    assert physical.entry == dict(path=str(tmp_path / "dense/first"),
                                  manifest_digest="sha256:" + "a" * 64)

    panel = tmp_path / "panel.json"
    panel.write_text(json.dumps(dict(jobs=[dict(recording="north"), dict(recording=trial.SOUTH)])))
    monkeypatch.setattr(trial, "PANEL_SHA", sha256(panel.read_bytes()).hexdigest())
    southern = trial.prefix_plan("public-south", panel, tmp_path)
    assert southern.edge == "upper"
    assert southern.entry == dict(path=str(tmp_path / trial.SOUTH),
                                  manifest_digest="sha256:" + trial.SOUTH_MANIFEST)
    with pytest.raises(ValueError, match="declared acquisition prefix"):
        trial.prefix_plan("DS30-0008", panel, tmp_path)


def documents():
    factor = dict(candidate_rank=1, integer_epoch_sample=3, fractional_epoch_offset_samples=0.,
                  fractional_tracking_cfo_hz=-5432., fractional_exact_score=.25,
                  fractional_control_score=.03, fractional_margin=.22,
                  passed_fractional_margin_gate=True)
    baseline = dict(
        clock_anchor={}, delivery_clocks=[], last_sample_counter=0,
        source=dict(raw_recording_authority_digest="same", probes=[
            dict(visit_index=0, receiver_id=0, candidates=[factor]),
            dict(visit_index=0, receiver_id=1, candidates=[]),
        ]),
        provenance=dict(window_count=1, processed_windows=1, invalid_capture=0,
                        excluded_windows=[], skipped_fast_score=0),
    )
    arms = {name: deepcopy(baseline) for name in ("deployed", "parent", "exact", "selected")}
    parent = arms["parent"]["source"]["probes"][0]["candidates"][0]
    parent["fractional_exact_score"] += 1e-14
    parent["fractional_margin"] += 1e-14
    return arms


def test_transfer_comparison_counts_rank_and_parent_score_changes():
    arms = documents()
    receipt = trial.compare(arms, [dict(parent=1000, exact=1100, selected=1200, deployed=3000)])
    assert receipt["selected_rank_counts"] == dict.fromkeys(arms, {1: 1})
    assert receipt["selected_vs_exact"] == pytest.approx(1200 / 1100 - 1)
    assert receipt["parent_differences"]["counts"] == dict(
        changed_availability=0, changed_selected_identity_or_gate=0, changed_score_rows=1,
    )
    assert receipt["parent_differences"]["max_abs_score_delta"]["fractional_margin"] > 0.
    assert len({receipt["probe_sha256"][key] for key in ("deployed", "exact", "selected")}) == 1


def test_transfer_comparison_rejects_changed_selected_bytes_and_probe_order():
    arms = documents()
    selected = arms["selected"]["source"]["probes"][0]["candidates"][0]
    selected["fractional_epoch_offset_samples"] = -0.
    with pytest.raises(ValueError, match="exact production acquisition rows"):
        trial.compare(arms, [])

    arms = documents()
    arms["parent"]["source"]["probes"].reverse()
    with pytest.raises(ValueError, match="probe ordering or metadata"):
        trial.compare(arms, [])
