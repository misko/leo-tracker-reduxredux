from leo.presentation import scanner_refinement as presentation
from leo.presentation.scanner_refinement import render_scanner_refinement
from tests.scanner.refinement_fixtures import comparison_fixture


def test_both_comparison_pngs_are_deterministic_and_empty_support_is_honest():
    evidence = comparison_fixture()
    a = render_scanner_refinement(evidence)
    assert a == render_scanner_refinement(evidence)
    assert set(a) == {"shift-recovery", "probe-comparison"}
    assert all(value.startswith(b"\x89PNG\r\n\x1a\n") for value in a.values())
    failed = evidence.model_copy(
        update={"rows": tuple(r.model_copy(update={"selected_rank": None}) for r in evidence.rows)}
    )
    assert all(value.startswith(b"\x89PNG") for value in render_scanner_refinement(failed).values())


def test_delay_induced_alias_jump_is_visible_in_raw_png(monkeypatch):
    evidence = comparison_fixture()
    rows = list(evidence.rows)
    index = next(i for i, r in enumerate(rows) if r.case == "delay" and r.profile == "joint512")
    candidate = rows[index].candidates[0]
    alias = 1 / 4.4e-6
    rows[index] = rows[index].model_copy(
        update={"candidates": (candidate.model_copy(update={"cfo_hz": 10000 + alias}),)}
    )
    figures = []
    monkeypatch.setattr(presentation, "_png", lambda figure: figures.append(figure) or b"PNG")
    render_scanner_refinement(evidence.model_copy(update={"rows": tuple(rows)}))
    raw = next(
        ax for ax in figures[1].axes if ax.get_ylabel() == "Raw delay-induced CFO error (Hz)"
    )
    assert abs(float(raw.collections[-1].get_offsets()[0, 1]) - alias) < 1e-8
    assert raw.get_yscale() == "symlog"
