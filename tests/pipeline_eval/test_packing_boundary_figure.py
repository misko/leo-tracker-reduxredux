from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from packing_boundary_figure import measurements


def test_figure_uses_paired_elapsed_orders_at_the_correct_boundaries():
    captures, guarded = measurements()
    assert [case for case, _ in captures] == ["DS30-0016", "DS30-0008"]
    for _, pairs in captures:
        assert len(pairs) == 3
        assert all(0 < packed < original for original, packed in pairs)
    (acquisition, first), (exit_label, through_exit) = guarded
    assert (acquisition, exit_label) == ("Acquisition", "Through exit")
    assert len(first) == len(through_exit) == 2
    for (a, b), (x, y) in zip(first, through_exit, strict=True):
        assert 0 < a < b < x < y
