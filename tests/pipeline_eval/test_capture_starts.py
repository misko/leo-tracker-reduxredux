import pytest

from tools.pipeline_eval.qualification.capture_starts import peak_rows
from tools.pipeline_eval.qualification.capture_starts_results import (
    basin_index,
    grid_peaks_search,
    near,
)


def test_attribution_uses_original_coarse_order_before_fine_reranking():
    chosen = peak_rows(((0.2, 700, -80000), (0.19, 700, 160000), (0.17, 940, 0)))
    winner = dict(coarse_epoch_sample=700, coarse_residual_cfo_hz=160000.0, coarse_score=0.19)
    assert basin_index(dict(centers=chosen), winner) == 2
    with pytest.raises(ValueError, match="one coarse basin"):
        basin_index(dict(centers=chosen), dict(winner, coarse_residual_cfo_hz=40000))


def test_fine_grid_ties_are_calibration_centered_and_preserve_actual_stage_epoch():
    fit = grid_peaks_search(
        [
            dict(epoch=440, cfo_grid_hz=[58000.0, 62000.0, 70000.0], scores=[0.38, 0.38, 0.32]),
        ],
        60500.0,
    )
    assert fit == [dict(epoch=440, cfo_hz=62000.0, score=0.38)]


def test_stage_link_checks_circular_epoch_before_numbering_cfo_neighbor():
    stage = [dict(epoch=5, cfo=1000), dict(epoch=13332, cfo=9000), dict(epoch=30, cfo=4100)]
    projected = near(stage, 0, 4000, lambda r: r["epoch"], lambda r: r["cfo"])
    assert projected["index"] == 1
    assert projected["distance_samples"] == 1
    assert projected["literal_cfo_difference_hz"] == 5000
