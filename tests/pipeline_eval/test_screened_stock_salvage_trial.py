from pathlib import Path
from runpy import run_path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture(scope="module")
def trial():
    return run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x"
                        / "screened_stock_salvage_trial.py"))


def test_compare_includes_empty_alternatives_and_preserves_active_mask(trial):
    trim = dict(start_index=1, stop_index=13, points=12, norad=121, candidate_index=2,
                alias=3, phase_s=4.0, cost=123.0)
    selected = dict(component="recovered", selected=trim, alternatives=[trim])
    incoming = [dict(component=name, points=points) for name, points in
                (("active", 30), ("recovered", 0), ("unrecovered", 0))]
    retained = [dict(component=name, points=points) for name, points in
                (("active", 30), ("recovered", 12), ("unrecovered", 0))]
    archived = dict(incoming=incoming, curved=retained, selected=[selected])
    [restored] = trial["recorded_stock_offers"]([archived])
    assert restored == dict(
        incoming=incoming, outgoing=retained,
        diagnostics=[selected, dict(component="unrecovered", selected=None, alternatives=[])],
    )
    offered = trial["offered_trims"]([restored])
    reversed_rows = dict(restored, diagnostics=restored["diagnostics"][::-1])
    assert trial["offered_trims"]([reversed_rows]) == offered
    adjusted = dict(selected, selected=dict(trim, phase_s=4.05))
    changed = dict(restored, diagnostics=[adjusted, restored["diagnostics"][1]])
    assert trial["offered_trims"]([changed]) != offered
    already_active = dict(archived, selected=[dict(selected, component="active")])
    with pytest.raises(ValueError, match="already active"):
        trial["recorded_stock_offers"]([already_active])


def test_salvage_instrumentation_observes_nested_calls_and_restores_kernel(trial):
    def profile(observed, prediction, inverse):
        return prediction.shape[0]

    def noise(residual, times):
        return residual.shape[0]

    def salvage(scan, node, keep, **options):
        assert options == {"rounds": 5}
        assert kernel.profile(None, np.empty((121, 0)), None) == 121
        assert kernel.profile(None, np.empty((81, 0)), None) == 81
        assert kernel.batch_noise_screen(np.empty((1, 0)), None) == 1
        return node + 1, "after", [{"component": "one"}]

    kernel = SimpleNamespace(salvage=salvage, profile=profile, batch_noise_screen=noise)

    def identity(scan, node, keep):
        return (scan, node, keep)

    with trial["trace_salvage"](kernel, identity) as (metrics, offers):
        assert kernel.salvage("scan", 0, "before", rounds=5) == (1, "after", [{"component": "one"}])
        assert kernel.profile is profile and kernel.batch_noise_screen is noise

    assert {key: value for key, value in metrics.items() if key.endswith("_calls")} == dict(
        fine_profile_calls=1, coarse_profile_calls=1, noise_calls=1, salvage_calls=1,
    )
    assert offers == [dict(diagnostics=[{"component": "one"}], incoming=("scan", 0, "before"),
                           outgoing=("scan", 1, "after"))]
    assert kernel.salvage is salvage
