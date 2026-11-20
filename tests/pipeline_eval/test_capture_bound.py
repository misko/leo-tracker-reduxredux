import ctypes as ct
from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.qualification.capture_bound_trial import bound_statistics
from tools.pipeline_eval.variants import capture_bound


def manual(envelope, x, template, starts, ends, frames, width, per_tap):
    output = np.empty(width, dtype="<f8")
    terms, supports = ct.c_uint64(), ct.c_uint64()
    status = envelope.call(
        x.ctypes.data,
        x.size,
        template.ctypes.data,
        template.size,
        starts.ctypes.data,
        ends.ctypes.data,
        starts.size,
        frames.ctypes.data,
        frames.size,
        width,
        per_tap,
        output.ctypes.data,
        ct.byref(supports),
        ct.byref(terms),
    )
    assert status == 0
    return output, terms.value, supports.value


def brute(x, ref, starts, ends, frames, limit, frequencies):
    grid = np.zeros((len(frequencies), limit))
    for j, f in enumerate(frequencies):
        for e in range(limit):
            values = []
            for a, b in zip(starts, ends, strict=True):
                r = ref[a:b] * np.exp(2j * np.pi * f * np.arange(b - a))
                for s in frames:
                    y = x[s + a + e : s + b + e]
                    if len(y) != len(r):
                        continue
                    energy = np.linalg.norm(r) * np.linalg.norm(y)
                    values.append(abs(np.vdot(r, y)) / energy if energy else 0.0)
            grid[j, e] = np.mean(values)
    return grid


def test_grouped_and_per_tap_envelopes_include_every_reference_score(tmp_path):
    library = capture_bound.Envelope(capture_bound.build(tmp_path / "bounds.so"))
    rng = np.random.default_rng(26003)
    raw = rng.integers(-2048, 2049, size=89) + 1j * rng.integers(-2048, 2049, size=89)
    template = rng.uniform(-1, 1, size=55) + 1j * rng.uniform(-1, 1, size=55)
    raw[30:49] = 0
    starts, ends, frames = (np.array(x, dtype=np.intp) for x in ((2, 25), (18, 44), (0, 16, 65)))
    geometry = (raw, template, starts, ends, frames, 18)
    four, four_terms, support = manual(library, *geometry, False)
    tap, tap_terms, tap_support = manual(library, *geometry, True)
    scores = brute(*geometry, (0, 0.07, 0.17, 0.3))
    assert support == tap_support and tap_terms > four_terms
    assert np.all(scores <= tap[None, :])
    assert np.all(tap <= four)
    assert bound_statistics(scores, tap, 1.0)["violations"] == 0


def test_only_exact_silence_short_circuits_and_scope_restores(tmp_path):
    build = capture_bound.Envelope(capture_bound.build(tmp_path / "bounds.so"))
    original = lambda *_args: "original"  # noqa: E731
    acquisition = SimpleNamespace(_folded_anchor_score_grid=original)
    args = (
        np.zeros(200000, dtype=complex),
        np.ones(13333, dtype=complex),
        10_000_000,
        (0.0,),
        (3,),
        13333,
    )
    with build.activate(acquisition):
        (scores,) = acquisition._folded_anchor_score_grid(*args)
        assert not scores.any()
        assert build.rows[-1]["omitted_cells"] == 13333
        assert acquisition._folded_anchor_score_grid(args[0][:16], *args[1:]) == "original"
        assert build.rows[-1]["omitted_cells"] == 0
    assert acquisition._folded_anchor_score_grid is original


def test_rank_cut_keeps_equal_bounds_and_no_cutoff_keeps_all_columns():
    scores = np.array([[0.1, 0.2, 0.3]])
    upper = np.array([0.2, 0.25, 0.3])
    assert bound_statistics(scores, upper, 0.25)["optimistic_cut_columns"] == 1
    assert bound_statistics(scores, upper, None)["optimistic_cut_columns"] == 0
