"""The new local refinement must inherit its assignments from the RF-only map."""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


def test_freeze_uses_training_mode_and_rejects_changed_inputs(tmp_path, monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "wide_polish", directory / "polish_randomized_wide_mode.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run, evidence = tmp_path / "run", tmp_path / "evidence"
    run.mkdir()
    (evidence / "evidence").mkdir(parents=True)
    tle = evidence / "evidence" / "orbit.tle"
    tle.write_text("opaque fixture; freeze does not propagate")
    source = evidence / "evidence" / "scan.json"
    doc = dict(
        inventory=dict(partition="randomized", tle_file=tle.name, tle_digest=module.digest(tle))
    )
    source.write_text(json.dumps(doc))
    parent = dict(
        complete=True,
        position_truth_used=False,
        prior_matched_norads_used=False,
        partition="randomized",
        clock_s=0,
        altitude_m=0,
        scan_count=1,
        best_index=1,
    )
    (run / "result.json").write_text(json.dumps(parent))
    history = [
        dict(
            session_id="scan",
            source_digest=module.digest(source),
            tle_digest=module.digest(tle),
            episodes=[dict(episode_id=str(i)) for i in range(4)],
        )
    ]
    (run / "history.json").write_text(json.dumps(history))
    for name in ["grid", "accumulated"]:
        np.savez(run / (name + ".npz"), unused=[0])
    np.savez(
        run / "scan.npz",
        signal_weight=np.full((4, 2), 0.99),
        best_train_rms_hz=[[10, 10], [10, 10], [10, 10], [10, 600]],
        best_norad=[[900, 100], [901, 101], [902, 102], [903, 103]],
        heldout_logbf=np.full((4, 2), 1e99),
    )
    _, assignments, _ = module.freeze_assignments(run, evidence)
    assert [a["norad"] for a in assignments] == [100, 101, 102]
    parent["clock_s"] = -0.225
    (run / "result.json").write_text(json.dumps(parent))
    assert module.freeze_assignments(run, evidence)[1] == assignments
    source.write_text(source.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        module.freeze_assignments(run, evidence)
    parent["position_truth_used"] = True
    (run / "result.json").write_text(json.dumps(parent))
    with pytest.raises(ValueError, match="RF-only"):
        module.freeze_assignments(run, evidence)
