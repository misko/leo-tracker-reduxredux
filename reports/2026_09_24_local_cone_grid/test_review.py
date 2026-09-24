"""Independent selection-isolation tests for the local TRAIN grid."""

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "local_cone_grid_review", Path(__file__).with_name("run.py")
)
RUN = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUN)


def _row(east_km, north_km, training_loss, held_loss):
    return {
        "east_km": east_km,
        "north_km": north_km,
        "methods": {
            "baseline": {
                "training_capped_loss": training_loss,
                "held_capped_loss": held_loss,
            }
        },
    }


def test_refinement_seed_uses_training_loss_not_held_loss():
    rows = [_row(-5.0, 5.0, 0.2, 0.9), _row(5.0, -5.0, 0.3, 0.01)]
    winner = RUN.best_one(rows, "baseline")
    assert (winner["east_km"], winner["north_km"]) == (-5.0, 5.0)

    # A large held-only mutation cannot alter the next refinement seed.
    rows[0]["methods"]["baseline"]["held_capped_loss"] = 0.0
    rows[1]["methods"]["baseline"]["held_capped_loss"] = 1.0
    same_winner = RUN.best_one(rows, "baseline")
    assert (same_winner["east_km"], same_winner["north_km"]) == (-5.0, 5.0)


def test_training_ties_have_deterministic_coordinate_order():
    rows = [_row(1.0, -2.0, 0.2, 0.8), _row(-1.0, 2.0, 0.2, 0.1)]
    winner = RUN.best_one(rows, "baseline")
    assert (winner["east_km"], winner["north_km"]) == (-1.0, 2.0)


def test_search_runner_has_no_reference_coordinate_constant():
    source = Path(__file__).with_name("run.py").read_text()
    assert "REFERENCE =" not in source
    assert "reference_latitude" not in source
