from collections import namedtuple
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("named_history_once")


Catalogue = namedtuple("Catalogue", ("names", "satellite_numbers", "satellites"))


def fixture():
    old = Catalogue(("a", "b", "unselected"), (91, 42, 30), (object(), object(), object()))
    scan = SimpleNamespace(norads=(42, 91), previous_tle="unchanged", previous_tle_sha256="causal",
                           origin_utc_ns=12, previous_sources={"42": {"source": "old-42"}, "91": {"source": "old-91"}})

    def subset(data, rows):
        return Catalogue(*(tuple(field[i] for i in rows) for field in data))

    def states(catalogue, origin, times):
        assert origin == 12
        assert np.array_equal(times, (0., 150., 300.))
        return None, None, np.asarray([n != 42 for n in catalogue.satellite_numbers])

    return old, scan, subset, states


def test_original_success_needs_no_recovery(trial):
    expected = object()
    trace = []
    def previous(scan, labels):
        trace.append((scan, labels))
        return expected

    modes = SimpleNamespace(previous_bank=previous, parse_element_sets=None)
    retained = SimpleNamespace(previous_bank=previous)
    events = []
    with trial.recover_previous(modes, retained, None, events):
        assert retained.previous_bank("ordinary", (0,)) is expected
    assert trace == [("ordinary", (0,))] and not events
    assert modes.previous_bank is retained.previous_bank is previous


def test_specific_causal_assertion_recovers_only_the_failed_selected_orbit(trial):
    old, scan, subset, states = fixture()
    seen = []
    parser = lambda previous: old

    def previous(scan, labels):
        data = modes.parse_element_sets(scan.previous_tle)
        cat = subset(data, [data.satellite_numbers.index(scan.norads[j]) for j in labels if scan.norads[j] in data.satellite_numbers])
        sample = np.array([0., 150., 300.])
        _, _, good = modes.ecef_states(cat, scan.origin_utc_ns, sample)
        seen.append(cat.satellite_numbers)
        if not good.all():
            raise AssertionError
        return cat.satellite_numbers

    modes = SimpleNamespace(previous_bank=previous, ecef_states=states, parse_element_sets=parser)
    retained = SimpleNamespace(previous_bank=previous)
    events = []
    assertion = previous.__code__.co_firstlineno + 7
    with trial.recover_previous(modes, retained, subset, events, line=assertion):
        assert modes.previous_bank(scan, (0, 1)) == (91,)
    assert seen == [(42, 91), (91,)]
    assert events[0]["failed_previous_norads"] == [42]
    assert events[0]["previous_sources"] == {"42": {"source": "old-42"}}
    assert modes.parse_element_sets is parser and modes.previous_bank is previous


def test_unrelated_assertion_and_missing_provenance_remain_visible(trial):
    old, scan, subset, states = fixture()
    events = []
    sentinel = AssertionError("independent fit error")

    def unrelated(scan, labels):
        raise sentinel

    modes = SimpleNamespace(previous_bank=unrelated, ecef_states=states, parse_element_sets=lambda previous: old)
    retained = SimpleNamespace(previous_bank=unrelated)
    with trial.recover_previous(modes, retained, subset, events, line=unrelated.__code__.co_firstlineno + 1):
        with pytest.raises(AssertionError, match="independent fit error") as caught:
            modes.previous_bank(scan, (0,))
    assert caught.value is sentinel and not events

    def malformed(scan, labels):
        cat = subset(old, (1,))
        sample = np.array([0., 150., 300.])
        _, _, good = states(cat, scan.origin_utc_ns, sample)
        if not good.all():
            raise AssertionError

    modes.previous_bank = retained.previous_bank = malformed
    scan.previous_sources = {}
    with trial.recover_previous(modes, retained, subset, events, line=malformed.__code__.co_firstlineno + 5):
        with pytest.raises(AssertionError):
            modes.previous_bank(scan, (0,))
    assert not events
