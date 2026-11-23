import pytest

from reports.ALGO08.v3.short_cfo_refine import amend, factor_reference


def factor(hz=-421_001.0, epoch=6, offset=-0.25, rank=0):
    return (rank, epoch, offset, hz, 0.52, 0.09)


def evidence(
    *, full=80.0, prefix=20.0, tail=120.0, low=0.80, high=0.90, exact=0.24, rolled=0.01, frames=5.0
):
    return (full, prefix, tail, low, high, exact, rolled, frames)


@pytest.mark.parametrize("hz", [-421_001.0, 421_001.0])
def test_supported_remeasurement_changes_only_signed_frequency(hz):
    original = (factor(hz),)
    changed, status = amend(original, evidence(full=-80.0), 1.0, 0.0)
    assert status == "updated"
    assert changed[0][3] == hz - 80.0
    assert changed[0][:3] + changed[0][4:] == original[0][:3] + original[0][4:]


@pytest.mark.parametrize(
    "diagnostics",
    [
        None,
        evidence(exact=0.0, rolled=0.0),
        evidence(frames=3.0),
        evidence(low=0.69),
        evidence(tail=-400.1),
        evidence(full=250.1),
        evidence(full=float("nan")),
    ],
)
def test_fallback_retains_exact_original_detection(diagnostics):
    original = (factor(),)
    changed, status = amend(original, diagnostics, 1.0, 0.0)
    assert changed is original
    assert status != "updated"


def test_no_new_detection_or_alias_boundary_crossing():
    assert amend((), evidence(), 1.0, 0.0)[0] == ()
    original = (factor(hz=799_960.0),)
    assert amend(original, evidence(), 1.0, 0.0) == (original, "alias_boundary")


def test_primary_reference_is_selected_before_refinement_and_cfo_remains_signed():
    original = factor(hz=-421_011.0, epoch=0, offset=-0.25)
    reference = factor(hz=-421_001.0, epoch=13_332, offset=0.65)
    secondary = factor(hz=421_011.0, epoch=0, offset=-0.25, rank=1)
    found, delta = factor_reference([secondary, reference], original)
    assert found == reference
    assert delta["matched"]
    assert delta["samples"] == pytest.approx(0.10)
    assert delta["hz"] == -10.0
    assert factor_reference([secondary], original) == (None, None)
    opposite = factor(hz=421_011.0, epoch=0, offset=-0.25)
    assert not factor_reference([opposite], original)[1]["matched"]
