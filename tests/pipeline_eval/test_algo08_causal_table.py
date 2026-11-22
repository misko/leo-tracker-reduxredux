from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest
from sgp4.api import accelerated

from leo.analysis.localization_v3 import orbit_modes
from leo.analysis.localization_v3.orbits import ecef_states
from leo.application import localization_v3 as application
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day
from tests.operations.test_localization_v3_inputs import fixture
from tools.pipeline_eval.variants.algo08_causal_reuse import CausalPreparationParser
from tools.pipeline_eval.variants.algo08_causal_table import causal_table


def test_causal_table_preserves_epoch_retrieval_and_forecast_receipts(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(-6000, 230), (-5000, 231.9), (-4000, 232.5),
                                                 (-3000, 232.5), (-2000, 234), (1000, 232.9)])

    class Snapshot(SimpleNamespace):
        def __lt__(self, other):
            return self.collected_utc_ns < other.collected_utc_ns

    snapshots = tuple(Snapshot(**vars(s)) for s in reader.list_snapshots("space-track"))
    reader.list_snapshots = lambda _: snapshots
    metadata = dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff)

    def run():
        parser = CausalPreparationParser()
        sky = application.prepare_initial_sky(reader, [dict(times=[0., 250.])], metadata,
                                               screen_latitude_deg=10., screen_longitude_deg=20.,
                                               element_parser=parser)
        history = application.prepare_phase_history(reader, sky["nominal_elements"], metadata,
                                                    element_parser=parser)
        return sky, history, application.forecast(history)

    expected = run()
    original_reads = list(reads)
    reads.clear()
    with causal_table(canonical_exports=True) as counts:
        actual = run()
        assert counts["forecast_calls"] == 1
        if accelerated:
            assert counts["canonical_export_hits"] > 0
    assert actual[:2] == expected[:2]
    np.testing.assert_equal(actual[2], expected[2])
    assert original_reads == reads


def test_composed_prior_cache_is_scoped_and_stock_digest_check_is_preserved():
    old = at_day(231)
    newer = at_day(232)
    catalogue = parse_element_sets(newer)
    origin, = catalogue.element_epoch_utc_ns()
    times = np.arange(-20., 321.)
    position, velocity, good = ecef_states(catalogue, origin, times)
    assert good.all()
    sky = dict(time_s=times, position_km=position, velocity_km_s=velocity)

    def scan(text):
        return SimpleNamespace(previous_tle=text, previous_tle_sha256=sha256(text.encode()).hexdigest(),
                               norads=catalogue.satellite_numbers, origin_utc_ns=origin, sky=sky)

    expected = orbit_modes.previous_bank(scan(old), [0])
    operation = orbit_modes.parse_element_sets
    with causal_table(previous_catalogues=True) as counts:
        first = scan(old)
        a = orbit_modes.previous_bank(first, [0])
        b = orbit_modes.previous_bank(scan(old), [0])
        other = orbit_modes.previous_bank(scan(newer), [0])
        first.previous_tle = newer
        with pytest.raises(ValueError, match="bytes differ"):
            orbit_modes.previous_bank(first, [0])
    assert orbit_modes.parse_element_sets is operation
    for result in (a, b):
        assert result[1:] == expected[1:]
        for key, values in expected[0].items():
            np.testing.assert_array_equal(result[0][key], values)
    assert other[2] != expected[2]
    if accelerated:
        assert counts["distinct_previous_parse_hits"] == 1
        assert counts["distinct_previous_parse_calls"] == 2
