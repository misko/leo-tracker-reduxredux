"""Full DS30 figures preserve pair membership and all-assigned error coverage."""

import csv
from pathlib import Path
import sys

from PIL import Image
import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
import full_successor_figures as figures


ENROLLED = {"a": True, "b": False, "c": False}


def row(case, role, first, *, clock, cpu, outcome="complete", c0=None, fitted=None):
    return dict(case=case, first=first, release_100=int(ENROLLED[case]), algorithm=role, outcome=outcome,
                elapsed_s=clock, cpu_s=cpu, c0_error_km=c0, fitted_c_error_km=fitted, original_field="permitted",
                c0_fix=outcome == "complete", fitted_c_fix=int(outcome == "complete"))


@pytest.fixture
def rows():
    return [
        row("a", "installed", "installed", clock=12, cpu=9, c0=0, fitted=3),
        row("a", "successor", "installed", clock=6, cpu=5, outcome="withheld"),
        row("b", "installed", "successor", clock=4, cpu=1, outcome="invalid_publication"),
        row("b", "successor", "successor", clock=2, cpu=2.5),
        row("c", "installed", "successor", clock=2, cpu=1.2, outcome="worker_failed"),
        row("c", "successor", "successor", clock=4, cpu=3, c0=.08, fitted=5),
    ]


def scored_file(tmp_path, rows):
    path = tmp_path / "recordings.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_pair_membership_order_and_nonfix_error_mass(tmp_path, rows):
    pairs = figures._read_pairs(scored_file(tmp_path, rows[::-1]), ENROLLED)
    assert [pair["release_100"] for pair in pairs] == [True, False, False]
    runtime = figures._runtime_series(pairs, "elapsed_s")
    assert [line[2] for line in runtime] == [[12, 4, 2], [6, 2, 4]]
    speed = figures._order_series(pairs, "elapsed_s")
    assert [line[2:] for line in speed] == [([2], 1), ([2, .5], 2)]
    speed_cpu = figures._order_series(pairs, "cpu_s")
    assert speed_cpu[0][2] == [1.8]
    assert speed_cpu[1][2] == pytest.approx([.4, .4])
    errors = figures._error_series(pairs, "c0")
    assert [line[2:] for line in errors] == [([0], 3), ([.08], 3)]
    assert "1 scored, 2 fixes of 3 assigned" in errors[1][0]
    x, y = figures._percent_ecdf(errors[0][2], errors[0][3], 0, 1)
    assert x == [0, 0, 1]
    assert y == [0, pytest.approx(100/3), pytest.approx(100/3)]
    assert figures._percent_ecdf([], 3, 0, 1) == ([0, 1], [0, 0])
    assert figures._percent_ecdf([0, 0], 3, 0, 1)[1][-1] == pytest.approx(200/3)


@pytest.mark.parametrize(("change", "message"), (
    ({"algorithm": "installed"}, "Duplicate"),
    ({"first": "successor"}, "inconsistent first"),
    ({"release_100": "0"}, "subset"),
    ({"case": "unassigned"}, "Unenrolled"),
    ({"elapsed_s": "inf"}, "Invalid scored measurement"),
    ({"cpu_s": ""}, "Missing through-exit clock"),
    ({"c0_error_km": 1}, "without a fix"),
    ({"c0_fix": True}, "disagrees with terminal outcome"),
))
def test_inconsistent_rows_are_rejected(tmp_path, rows, change, message):
    rows[1].update(change)
    with pytest.raises(ValueError, match=message):
        figures._read_pairs(scored_file(tmp_path, rows), ENROLLED)


def test_missing_role_or_underfilled_population_produces_no_report_pngs(tmp_path, rows):
    path = scored_file(tmp_path, rows[:-1])
    with pytest.raises(ValueError, match="Both scored roles"):
        figures._read_pairs(path, ENROLLED)
    output = tmp_path/"report"
    with pytest.raises(ValueError, match="455-case"):
        figures.render_distribution_figures(path, output, enrollment=ENROLLED)
    assert not output.exists()


def test_figure_panels_keep_own_legends_and_error_extents(tmp_path, rows):
    pairs = figures._read_pairs(scored_file(tmp_path, rows), ENROLLED)
    runtime = figures._figure(pairs, runtime=True)
    error = figures._figure(pairs, runtime=False)
    assert len(runtime.axes) == 8
    assert len(error.axes) == 4
    assert not runtime.legends and not error.legends
    assert all(ax.get_legend() is not None for ax in runtime.axes + error.axes)
    assert error.axes[0].get_xlim() != error.axes[1].get_xlim()
    assert any("1 paired exits" in t.get_text() for t in runtime.axes[2].get_legend().get_texts())
    outputs = figures._write_figures(pairs, tmp_path/"test-renders")
    assert [path.name for path in outputs] == ["runtime.png", "position-error.png"]
    for path, size in zip(outputs, [(2145, 1260), (1530, 1260)], strict=True):
        with Image.open(path) as image:
            assert image.size == size
            image.verify()


@pytest.mark.parametrize(("runtime", "full_counts", "subset_counts"), (
    (True, [3, 3], [1, 1]), (False, [1, 1], [1, 0]),
))
def test_histograms_use_shared_edges_and_count_actual_samples(tmp_path, rows, runtime, full_counts, subset_counts):
    pairs = figures._read_pairs(scored_file(tmp_path, rows[::-1]), ENROLLED)
    plot = figures._histogram_figure(pairs, runtime=runtime)
    assert len(plot.axes) == 4
    for metric in (0, 1):
        full, subset = plot.axes[metric], plot.axes[metric + 2]
        base_edges = full.patches[0].get_data().edges.tolist()
        for panel, expected in ((full, full_counts), (subset, subset_counts)):
            assert panel.get_legend() is not None
            histograms = [patch.get_data() for patch in panel.patches]
            assert [data.edges.tolist() for data in histograms] == [base_edges, base_edges]
            assert [sum(data.values) for data in histograms] == expected
        if runtime:
            assert base_edges[0] > 0
            assert any("3 timed exits" in text.get_text() for text in full.get_legend().get_texts())
        else:
            assert base_edges[0] == 0
            labels = [text.get_text() for text in full.get_legend().get_texts()]
            assert "1/3 scored" in labels[0] and "0 withheld · 2 failed · 0 unscored fixes" in labels[0]
            assert "1/3 scored" in labels[1] and "1 withheld · 0 failed · 1 unscored fixes" in labels[1]


def test_histograms_keep_extremes_and_render_empty_error_cohort():
    edges = figures._histogram_edges([0, .0001, 2500], runtime=False)
    assert min(edges) == 0 and max(edges) == 2500
    equal_clocks = figures._histogram_edges([3, 3], runtime=True)
    assert min(equal_clocks) < 3 < max(equal_clocks)

    cases = [dict(release_100=True, installed=dict(outcome="withheld", c0_error_km=None, fitted_c_error_km=None),
                  successor=dict(outcome="solver_failed", c0_error_km=None, fitted_c_error_km=None))]
    error = figures._histogram_figure(cases, runtime=False)
    assert all(ax.texts[0].get_text() == "No scored fixes" for ax in error.axes)
    assert all(sum(patch.get_data().values) == 0 for ax in error.axes for patch in ax.patches)


def test_speed_and_error_keep_pairs_and_both_calibration_signs():
    def arm(wall, zero, fitted):
        return dict(elapsed_s=wall, c0_error_km=zero, fitted_c_error_km=fitted)

    pairs = [(arm(10, 1, 1), arm(5, .5, 1.5)), (arm(2, .5, .5), arm(5, .5, .5)),
             (arm(3, 1, None), arm(1, 0, None))]
    assert figures.paired_speed_errors(pairs, ("c0",)) == [(2, -.5), (.4, 0), (3, -1)]
    assert figures.paired_speed_errors(pairs, ("c0", "fitted_c")) == [(2, .5), (.4, 0)]
    plot = figures.paired_change_figure(pairs, "Paired fixes")
    assert [len(ax.collections[-1].get_offsets()) for ax in plot.axes] == [3, 2]
    empty = figures.paired_change_figure([], "No observations")
    assert all(any("No pairs" in t.get_text() for t in ax.texts) for ax in empty.axes)
