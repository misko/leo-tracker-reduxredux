import json
import sys
from pathlib import Path

import numpy as np


def test_report_without_height_uses_current_results_and_clock_replay(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "tools"))
    import report_wide_position as module

    row = dict(latitude_deg=40.0, longitude_deg=-100.0, label="current-fit")
    polish = tmp_path / "polish"
    polish.mkdir()
    (polish / "inference.json").write_text(
        json.dumps(
            dict(
                complete=True,
                position_truth_used=False,
                prior_matched_norads_used=False,
                models=[row],
                exact_clock_refit=row,
                leave_satellite_fold_out=[],
            )
        )
    )
    for name in ["inputs.json", "exact-inputs.json"]:
        (polish / name).write_text("{}")
    np.savez(polish / "states.npz", y=[1])
    grid = tmp_path / "grid"
    grid.mkdir()
    for name in ["result.json", "history.json", "configuration.json"]:
        (grid / name).write_text("{}")
    np.savez(grid / "grid.npz", east_km=[0, 1], north_km=[0, 1])
    np.savez(grid / "accumulated.npz", train=[1, 2])
    reference = tmp_path / "reference.json"
    reference.write_text(json.dumps(dict(latitude_deg=40, longitude_deg=-100)))
    clock = tmp_path / "bounded-clocks.json"
    clock.write_text(json.dumps(dict(models=[dict(row, selection="all")])))
    output = tmp_path / "report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report",
            "--coarse",
            str(grid),
            "--fine",
            str(grid),
            "--polish",
            str(polish),
            "--reference",
            str(reference),
            "--output",
            str(output),
            "--clock-replay",
            str(clock),
        ],
    )
    module.main()
    evaluation = json.loads((output / "evaluation.json").read_text())
    assert [r["label"] for r in evaluation["models"]] == [
        "current-fit",
        "bounded-clocks:all",
        "exact-clock-refit",
    ]
    assert all(r["error_m"] == 0 for r in evaluation["models"])
    assert (output / "wide-to-local.png").read_bytes().startswith(b"\x89PNG")
    assert (output / clock.name).read_bytes() == clock.read_bytes()
    assert not (output / "height-inference.json").exists()
