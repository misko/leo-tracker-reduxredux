import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def comparison(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "tools"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "selected_comparison", directory / "compare_selected_tracklets.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def rows(labels, receiver=1, residual=0, lift=0):
    return [
        {
            "observation_id": str(i),
            "receiver": receiver,
            "channel": 1,
            "track_id": label,
            "quality_status": "no_structure_detected",
            "residual_hz": residual,
            "alias_lift": lift,
        }
        for i, label in enumerate(labels)
    ]


def test_track_id_permutations_and_alias_offsets_do_not_change_grouping(comparison):
    first = rows([0, 0, 1, 1], lift=2)
    second = rows([8, 8, 3, 3], lift=-1, residual=20)
    result = comparison.pair_statistics(first, second[::-1])
    assert result["assignment_jaccard"] == result["common_pair_f1"] == 1
    assert result["relative_alias_inconsistent_points"] == 0
    assert result["prediction_difference_rms_hz"] == 20


def test_unassociated_points_are_not_a_shared_cluster(comparison):
    result = comparison.pair_statistics(rows([0, 0, -1, -1]), rows([3, 3, 4, -1]))
    assert result["both_assigned"] == 2
    assert result["only_b"] == 1
    assert result["neither_assigned"] == 1
    assert result["assignment_jaccard"] == pytest.approx(2 / 3)
    assert result["same_track_pairs_both"] == 1
    assert result["common_pair_f1"] == 1


def test_fragmentation_is_visible_when_coverage_is_identical(comparison):
    result = comparison.pair_statistics(rows([0, 0, 0, 0]), rows([1, 1, 2, 2]))
    assert result["assignment_jaccard"] == 1
    assert result["common_pair_f1"] == 0.5
    assert result["a_to_b_best_overlap_fraction"] == 0.5
    assert result["b_to_a_best_overlap_fraction"] == 1


def test_lane_mismatch_and_duplicate_ids_are_rejected(comparison):
    with pytest.raises(ValueError, match="lanes"):
        comparison.pair_statistics(rows([0, 0]), rows([0, 0], receiver=2))
    with pytest.raises(ValueError, match="Unique"):
        comparison.pair_statistics(rows([0, 0]), [rows([0])[0]] * 2)


def test_no_shared_associations_has_no_grouping_score(comparison):
    result = comparison.pair_statistics(rows([0, -1]), rows([-1, 1]))
    assert result["assignment_jaccard"] == 0
    assert result["common_pair_f1"] is None
    assert result["prediction_difference_rms_hz"] is None
