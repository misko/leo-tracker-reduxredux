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
