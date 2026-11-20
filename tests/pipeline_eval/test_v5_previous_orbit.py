import hashlib
from math import tau
from types import SimpleNamespace

import numpy as np
import pytest
from sgp4.api import WGS72, Satrec
from sgp4.exporter import export_tle

from leo.sky.propagation import ElementSetCatalogue, parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from tools.pipeline_eval.variants import v5_previous_orbit as candidate


class Scan:
    def __init__(self, current_motions, previous_motions):
        self.norads = np.array([63012, 63013])
        self.origin_utc_ns = 1_701_561_600_000_000_000
        self.sky = dict(time_s=np.arange(-17.0, 318.0),
                        position_km=np.zeros((2, 335, 3)), velocity_km_s=np.zeros((2, 335, 3)))
        self.elements = {
            str(number): dict(lines=elements(number, motion), provenance={"kind": "now"})
            for number, motion in zip(self.norads, current_motions, strict=True)
        }
        self.previous_tle = "".join("\n".join(elements(number, motion)) + "\n"
                                    for number, motion in previous_motions)
        self.previous_tle_sha256 = hashlib.sha256(self.previous_tle.encode()).hexdigest()
        self.previous_sources = {str(number): {"kind": "old"} for number, _ in previous_motions}


def elements(number, rate):
    sat = Satrec()
    sat.sgp4init(WGS72, "i", int(number), 27000, 0.0, 0.0, 0.0, .0005,
                 0.0, .8, 0.0, tau * rate / 1440, 0.0)
    return export_tle(sat)


def state(catalogue, origin, times):
    utc = origin + np.rint(times * 1e9).astype(np.int64)
    return propagate_grid(catalogue, SamplingGrid(tuple(map(int, utc)), 0, 1.0)), utc


def raw(catalogue, origin, times):
    result, utc = state(catalogue, origin, times)
    return result.error_code, utc


def ecef(catalogue, origin, times):
    result, _ = state(catalogue, origin, times)
    return result.position_teme_km, result.velocity_teme_km_s, result.usable


def guarded(timing=tuple(candidate.ALIGNMENT_S)):
    modes = SimpleNamespace(parse_element_sets=parse_element_sets, ecef_states=ecef)

    def previous_bank(scan, labels):
        assert hashlib.sha256(scan.previous_tle.encode()).hexdigest() == scan.previous_tle_sha256
        catalogue = modes.parse_element_sets(scan.previous_tle)
        p, v, good = modes.ecef_states(catalogue, scan.origin_utc_ns, np.asarray(timing))
        assert good.all()
        solution = {
            int(number): (p[k], v[k]) for k, number in enumerate(catalogue.satellite_numbers)
        }
        return {int(scan.norads[i]): solution.get(int(scan.norads[i])) for i in labels}

    modes.previous_bank = previous_bank
    receipt = dict(events=[], verification_wall_s=0.0, retry_wall_s=0.0)
    return candidate.history_guard(modes, ElementSetCatalogue, raw, receipt), receipt


def test_decayed_older_record_retries_using_the_same_valid_prior_and_full_current_inventory():
    repaired, receipt = guarded()
    mixed = Scan((15.1, 15.2), [(63012, 18.5), (63013, 15.2)])
    clean = Scan((15.1, 15.2), [(63013, 15.2)])
    result, oracle = repaired(mixed, [0, 1]), repaired(clean, [0, 1])
    assert result[63012] is None and oracle[63012] is None
    for current, expected in zip(result[63013], oracle[63013], strict=True):
        np.testing.assert_array_equal(current, expected)
    np.testing.assert_array_equal(mixed.norads, [63012, 63013])
    np.testing.assert_array_equal(parse_element_sets(mixed.previous_tle).satellite_numbers,
                                  [63012, 63013])
    assert receipt["events"][0]["missing_history"][0]["sgp4_codes"] == [6, 6, 6]
    assert receipt["events"][0]["retained_history_norads"] == [63013]
    repaired(mixed, [0, 1])
    assert len(receipt["events"]) == 1


def test_bad_current_orbit_fails_closed_despite_explicit_prior_decay():
    repair, receipt = guarded()
    bad = Scan((18.5, 15.2), [(63012, 18.5), (63013, 15.2)])
    with pytest.raises(ValueError, match="current orbit propagation failed"):
        repair(bad, [0, 1])
    assert receipt["events"] == []


def test_bad_older_padding_retains_its_original_hard_failure():
    repair, receipt = guarded((-10.0, 0.0, 20.0))
    scan = Scan((15.1, 15.2), [(63012, 18.5), (63013, 15.2)])
    with pytest.raises(AssertionError):
        repair(scan, [0, 1])
    assert receipt["events"] == []


def test_other_old_sgp4_error_codes_are_rejected():
    with pytest.raises(ValueError, match="outside the isolated decay contract"):
        candidate.decayed_rows([[0, 3, 6]], np.array([False]))
