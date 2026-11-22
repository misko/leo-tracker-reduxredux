from types import SimpleNamespace

import numpy as np
import pytest
from sgp4.api import accelerated
from sgp4.exporter import export_tle

from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.orbits import ecef_states
from leo.operations import localization_v3_inputs as inputs
from leo.sky.propagation import ElementSetError, parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day
from tests.operations.test_localization_v3_inputs import fixture
from tools.pipeline_eval.variants import algo08_causal_reuse as variant


def test_shared_element_states_and_exports_remain_exact():
    text = at_day(232) + at_day(232).replace("STARLINK-1008", "ALTERNATE NAME")
    variant_parser = variant.CausalPreparationParser()
    expected = ElementParser()(text)
    actual = variant_parser(text)
    origin = expected.element_epoch_utc_ns()[0]
    times = np.array([0., 1.3, 80., 124.])
    assert actual.names == expected.names
    assert actual.satellite_numbers == expected.satellite_numbers
    sat = actual.satellites[0]
    signature = sat.t, sat.error, sat.jdsatepoch, sat.jdsatepochF, export_tle(sat)
    for _ in range(2):
        fresh_states = ecef_states(expected, origin, times)
        shared_states = ecef_states(variant_parser(text), origin, times)
        for a, b in zip(fresh_states, shared_states, strict=True):
            np.testing.assert_array_equal(a, b)
    if accelerated:
        assert signature == (sat.t, sat.error, sat.jdsatepoch, sat.jdsatepochF, export_tle(sat))
        assert variant_parser.stats["element_hits"] == 1
        assert variant_parser.stats["element_misses"] == 1
        assert variant_parser.stats["snapshot_hits"] == 2
    else:
        assert variant_parser.stats["fallback_calls"] == 3


def test_preparation_preserves_history_inputs_and_archive_reads(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(-5000, 231.9), (-4000, 232.5),
                                                 (-3000, 232.5), (-2000, 234), (1000, 232.9)])
    class Snapshot(SimpleNamespace):
        def __lt__(self, other):
            return self.collected_utc_ns < other.collected_utc_ns

    snapshots = tuple(Snapshot(**vars(s)) for s in reader.list_snapshots("space-track"))
    reader.list_snapshots = lambda _: snapshots
    metadata = dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff)

    def run(parser):
        sky = inputs.prepare_initial_sky(reader, [dict(times=[0., 250.])], metadata,
                                         screen_latitude_deg=10., screen_longitude_deg=20.,
                                         element_parser=parser)
        history = inputs.prepare_phase_history(reader, sky["nominal_elements"], metadata,
                                              element_parser=parser)
        return sky, history

    expected = run(ElementParser())
    expected_reads = list(reads)
    reads.clear()
    actual = run(variant.CausalPreparationParser())
    assert expected == actual
    assert expected_reads == reads


@pytest.mark.parametrize("budget", [1, 256 * 1024 * 1024])
def test_bound_or_reused_text_never_hides_an_invalid_checksum(budget):
    parser = variant.CausalPreparationParser(budget)
    text = at_day(232)
    output = parser(text)
    assert output.element_epoch_utc_ns() == parse_element_sets(text).element_epoch_utc_ns()
    assert parser.stats["retained_peak_bytes"] <= budget
    assert bool(parser.stats["fallback_calls"]) == (budget == 1 or not accelerated)
    lines = text.splitlines()
    lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)
    with pytest.raises(ElementSetError, match="checksum"):
        parser("\n".join(lines))
