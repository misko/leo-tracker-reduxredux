import ast

import numpy as np
import pytest

from tools.pipeline_eval import cavity_runtime
from tools.pipeline_eval.variants import fit_basis

PHASE = "leo/analysis/research/shared_orbit_phase_fit.py"


def function(source, name):
    node = next(
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    scope = {"np": np, "group": lambda track: int(track["channel"] > 4), "REFERENCE_RF": 11.5e9}
    exec(compile(ast.Module([node], []), "<sealed-statistics>", "exec"), scope)
    return scope[name]


class Columns:
    def __init__(self, values):
        self.reads = 0
        self.values = values

    def __getitem__(self, key):
        self.reads += 1
        return self.values[key]


@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("correction", [0.0, -0.0, 14.5])
def test_fused_moments_preserve_all_fields_and_only_gather_the_frequency_once(order, correction):
    files = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    original = files[fit_basis.TARGET].decode()
    statistics = function(original, "statistics")
    augment = function(files[PHASE], "augment_phase_statistics")
    fused = function(fit_basis.revise(original), "statistics")
    rng = np.random.default_rng(20261119)
    times = np.sort(rng.uniform(8.0, 290.0, size=71))
    frequency = Columns(np.array(rng.uniform(-1e5, 1e5, size=(23, len(times))), order=order))
    derivative = np.array(rng.normal(1, 5, (23, len(times))), order=order)
    bank = dict(
        time_s=times,
        doppler_0=frequency,
        elevation_deg=rng.uniform(-5, 20, size=frequency.values.shape),
    )
    groups = []
    for index, supports in enumerate(((slice(1, 20), slice(8, 32)), (slice(30, 60),))):
        members = [
            dict(
                times=times[use],
                rf_hz=11.7e9,
                channel=index + 1,
                values=rng.normal(500, 2300, len(times[use])),
            )
            for use in supports
        ]
        groups.append((index, members))
    shifts = {"1": correction, "2": 0.0}
    moment = statistics(groups, bank, shifts)
    expected = augment(moment, times, frequency, derivative)
    assert frequency.reads == 6
    frequency.reads = 0
    actual = fused(groups, bank, shifts, phase_derivative=derivative)
    assert frequency.reads == 3
    assert actual.keys() == expected.keys()
    assert len(actual["fragments"]) == len(expected["fragments"])
    assert all(a is b for a, b in zip(actual["fragments"], expected["fragments"], strict=True))
    for key, value in expected.items():
        if isinstance(value, np.ndarray):
            assert actual[key].dtype == value.dtype
            assert actual[key].shape == value.shape
            assert actual[key].tobytes() == value.tobytes(), key
    plain = fused(groups, bank, shifts)
    assert plain.keys() == moment.keys()
    for key, value in moment.items():
        if isinstance(value, np.ndarray):
            assert plain[key].tobytes() == value.tobytes(), key


def test_fused_overlay_requires_both_original_discovery_calls():
    files = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    original = files[fit_basis.TARGET].decode()
    with pytest.raises(ValueError, match="unexpected compact discovery source or call sites"):
        fit_basis.revise(original.replace("phase_statistics(stats, scan.times", "missing(", 1))
