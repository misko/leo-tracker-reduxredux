import importlib.util
from pathlib import Path

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("timing", HERE / "run.py")
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def test_scale_selection_uses_only_train_full_blocks():
    rows = []
    for scale, value in ((0.2, 3.0), (1.0, 1.0), (5.0, 2.0)):
        for case, count in (("a", 72), ("b", 79)):
            for prior in ("sacramento", "reno"):
                rows.append(
                    {
                        "status": "completed",
                        "partition": "train",
                        "scan_count": count,
                        "model": "regularized_global_plus_scan_epoch_scale_x",
                        "scale_s": scale,
                        "penalized_train_objective": value,
                        "case_id": case,
                        "prior": prior,
                        "geographic_point_role": "shared",
                    }
                )
    winner, scores = timing.select_scale(rows)
    assert winner["scale_s"] == 1.0
    assert len(scores) == 3


def test_common_global_tie_break_is_deterministic():
    rows = [
        {"tau_s": -0.25, "training_capped_loss": 0.1},
        {"tau_s": 0.25, "training_capped_loss": 0.1},
        {"tau_s": 0.0, "training_capped_loss": 0.1},
    ]
    assert timing.choose_global(rows)["tau_s"] == 0.0
