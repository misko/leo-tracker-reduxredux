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
