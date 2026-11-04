import numpy as np
import pytest
from sgp4.exporter import export_tle

from leo.analysis.localization_v3.elements import ElementParser
from leo.sky.propagation import ElementSetError, parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day


def assert_equal(first, second):
    assert first.names == second.names
    assert first.satellite_numbers == second.satellite_numbers
    assert first.element_epoch_utc_ns() == second.element_epoch_utc_ns()
    for a, b in zip(first.satellites, second.satellites, strict=True):
        assert export_tle(a) == export_tle(b)
        for fraction in (.1, .25, .75):
            assert a.sgp4(2461274.5, fraction) == b.sgp4(2461274.5, fraction)


def test_reuse_is_exact_and_orbit_objects_are_never_shared():
    text = at_day(232)
    parser = ElementParser()
    cold = parser(text)
    cold.satellites[0].jdsatepoch += 1
    hit = parser(text)
    assert hit.satellites[0] is not cold.satellites[0]
    assert_equal(hit, parse_element_sets(text))
    assert parser.hits == parser.misses == 1


@pytest.mark.parametrize('budget', [0, 256 * 1024 * 1024])
def test_invalid_text_cannot_reuse_a_valid_catalogue(budget):
    text = at_day(232)
    parser = ElementParser(budget)
    assert_equal(parser(text), parse_element_sets(text))
    lines = text.splitlines()
    lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)
    for _ in range(2):
        with pytest.raises(ElementSetError, match='checksum'):
            parser('\n'.join(lines))
    assert parser.hits == 0


def test_bounded_eviction_and_bypass_preserve_results():
    text = at_day(232)
    parser = ElementParser()
    parser(text)
    parser.maximum_bytes = parser.bytes
    for day in (233, 232):
        assert_equal(parser(at_day(day)), parse_element_sets(at_day(day)))
    assert parser.evictions == 2
    assert parser.bytes <= parser.maximum_bytes
    uncached = ElementParser(0)
    for _ in range(2):
        assert_equal(uncached(text), parse_element_sets(text))
    assert uncached.bytes == uncached.hits == 0


def test_name_order_and_duplicate_objects_are_retained():
    text = at_day(232) + at_day(233).replace('STARLINK-1008', 'OTHER-NAME')
    parser = ElementParser()
    for _ in range(2):
        assert_equal(parser(text), parse_element_sets(text))
    assert np.array_equal(parser(text).satellite_numbers, [44714, 44714])
