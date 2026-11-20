from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from leo.analysis.starlink.fast_scan_fractional import fractional_take
from tools.pipeline_eval.variants import anchor_grid, anchor_receiver


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    library = tmp_path_factory.mktemp("anchor-filter") / "filter.so"
    anchor_receiver.compile_filter(library)
    return anchor_grid.native_grid(library)


@pytest.mark.parametrize("scale", (0.0, 1.0, 32000.0))
def test_whole_score_map_matches_capture_detector(native, scale):
    rng = np.random.default_rng(6187)
    values = scale * (rng.normal(size=3021) + 1j * rng.normal(size=3021))
    ref = rng.normal(size=99) + 1j * rng.normal(size=99)
    args = (values, ref, 1_000_000, (-52000.0, 0.0, 98643.0), (0, 1, 4, 8), 1333)
    exact = acquisition._folded_anchor_score_grid(*args)
    np.testing.assert_allclose(anchor_grid.score_grid(*args), exact, atol=3e-12, rtol=0)
    np.testing.assert_allclose(native(*args), exact, atol=4e-7, rtol=0)
    assert native(values, ref, 1_000_000, (), (0,), 1333) == ()
    with pytest.raises(ValueError, match="vectors"):
        native(values.reshape(3, -1), ref, 1_000_000, (0,), (0,), 33)


@pytest.mark.parametrize("radius", (0, 1, 3, 17))
@pytest.mark.parametrize("count", (0, 1, 17))
def test_peak_ties_wrap_plateaus_and_empty_maps(radius, count):
    freq = (1.0, -1.0, 5.0)
    for n in (0, 1, 2, 13):
        scores = tuple(
            row[:n] for row in np.random.default_rng(213).integers(0, 3, (3, 13)).astype(float)
        )
        args = (freq, scores, count, radius, 2.0, n)
        assert anchor_grid.retained_peaks(*args) == acquisition._retain_score_map_peaks(*args)


def test_single_fraction_and_fallback_have_same_values_and_support():
    source = np.random.default_rng(13).normal(size=(2, 90))
    source = source[0] + 1j * source[1]
    take = anchor_grid.fractional_sampler(fractional_take)
    for pos in ([8, 11], [9.125, 64.125], [9.1, 65.3], [[12.25, 23.25]], [], [20 + 1e-13]):
        np.testing.assert_array_equal(take(source, pos), fractional_take(source, pos))
    for pos in ([-1.0], [0.25], [np.nan]):
        with pytest.raises(ValueError):
            take(source, pos)


def test_partial_replay_replaces_values_and_checks_authority():
    def probe(visit, receiver):
        return dict(
            visit_index=visit,
            receiver_id=receiver,
            valid_start_counter=visit * 100,
            candidates=[{"score": 0.1}],
        )

    probes = [probe(v, r) for v in (1, 2) for r in (0, 1)]
    doc = dict(source={"probes": probes}, provenance={"run_id": "original"})
    native = deepcopy(probes[2:])
    native[1]["candidates"] = []
    replay = dict(
        producer={"run_id": "original"},
        archive_audit={"archive_exclusions_equal": True, "archive_sha256": "source"},
        source_sha256="py",
        kernel_sha256="kernel",
        rows=[dict(visit=2, equal_status=True, sample_start=200, iq_sha256="iq", native=native)],
    )
    updated, changed = anchor_receiver.splice_probes(doc, replay)
    assert changed == 1
    assert updated["source"]["probes"] == probes[:2] + native
    assert doc["source"]["probes"][3]["candidates"] == [{"score": 0.1}]
    assert updated["provenance"]["run_id"] != doc["provenance"]["run_id"]
    native[1]["valid_start_counter"] += 1
    with pytest.raises(ValueError, match="unbound"):
        anchor_receiver.splice_probes(doc, replay)
    native.pop()
    with pytest.raises(ValueError, match="geometry"):
        anchor_receiver.splice_probes(doc, replay)
