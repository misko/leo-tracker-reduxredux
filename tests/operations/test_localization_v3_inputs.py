import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from sgp4.exporter import export_tle

from leo.analysis.localization_v3.elements import ElementParser
from leo.operations import localization_v3_inputs as inputs
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day


def fixture(monkeypatch, entries):
    cutoff = parse_element_sets(at_day(233)).element_epoch_utc_ns()[0]
    snapshots = []
    for offset, day in entries:
        text = at_day(day)
        sha = hashlib.sha256(text.encode()).hexdigest()
        snapshots.append(SimpleNamespace(collected_utc_ns=cutoff+offset, sha256=sha,
                                         digest='sha256:'+sha, provider='space-track', text=text))
    reads = []

    def read(snapshot):
        assert snapshot.collected_utc_ns <= cutoff
        reads.append(snapshot)
        return snapshot.text

    def region(catalogue, origin, duration, **kwargs):
        assert origin == cutoff and duration == 300
        assert kwargs == dict(screen_latitude_deg=10., screen_longitude_deg=20.)
        return dict(catalogue=catalogue, source_indices=np.arange(len(catalogue)), bank={})

    monkeypatch.setattr(inputs, 'regional_bank', region)
    return cutoff, SimpleNamespace(list_snapshots=lambda _: snapshots, read=read), reads


def prepare(reader, cutoff):
    return inputs.prepare_initial_sky(reader, [dict(times=[0., 250.])],
                                      dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff),
                                      screen_latitude_deg=10., screen_longitude_deg=20.)


def test_recovery_catalogue_keeps_causal_48_to_72_hour_evidence(monkeypatch):
    hour = 3600*1_000_000_000
    cutoff, reader, reads = fixture(monkeypatch, [(-60*hour, 230.5),
                                                (hour, 233.1), (-80*hour, 229.)])
    result = inputs.prepare_recovery_catalogue(reader, cutoff)
    assert result['cutoff_utc_ns'] == cutoff and set(result['elements']) == {'44714'}
    row = result['elements']['44714']
    assert row['collected_utc_ns'] == cutoff-60*hour
    assert 48*hour < cutoff-row['element_epoch_utc_ns'] <= 72*hour
    assert len(reads) == 1
    assert parse_element_sets('\n'.join(row['lines'])).satellite_numbers == (44714,)


def test_latest_and_previous_are_causal_and_distinct(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(-2000, 231.9), (-1000, 232.5),
                                                 (-500, 234), (100, 232.9)])
    result = prepare(reader, cutoff)
    nominal = result['nominal_elements']['44714']
    assert nominal['provenance']['element_epoch_utc_ns'] < cutoff
    previous = parse_element_sets(result['previous_tle']).element_epoch_utc_ns()[0]
    assert previous < nominal['provenance']['element_epoch_utc_ns']
    assert result['metadata']['snapshot_count'] == 3
    assert len(reads) == 9
    assert result['previous_receipt']['catalogue_sha256'] == hashlib.sha256(
        result['previous_tle'].encode()).hexdigest()


def test_equal_epoch_does_not_create_previous_evidence(monkeypatch):
    cutoff, reader, _ = fixture(monkeypatch, [(-2000, 232.5), (-1000, 232.5)])
    with pytest.raises(ValueError, match='no previous causal'):
        prepare(reader, cutoff)


def test_old_collection_is_not_read_but_old_previous_epoch_is_preserved(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(-172800_000_000_001, 232.9),
                                                 (-2000, 220), (-1000, 232.5)])
    result = prepare(reader, cutoff)
    assert len(reads) == 6
    assert parse_element_sets(result['previous_tle']).element_epoch_utc_ns()[0] < (
        cutoff - 172800_000_000_000)


def test_missing_archive_is_explicit(monkeypatch):
    cutoff, reader, _ = fixture(monkeypatch, [(100, 232.9)])
    with pytest.raises(ValueError, match='no past TLE'):
        prepare(reader, cutoff)


def test_subsecond_epoch_is_not_an_independent_prior_update(monkeypatch):
    cutoff, reader, _ = fixture(monkeypatch, [(-3000, 231.9), (-2000, 232.49999999),
                                              (-1000, 232.5)])
    result = prepare(reader, cutoff)
    initial = parse_element_sets(result['previous_tle']).element_epoch_utc_ns()[0]
    repaired = parse_element_sets(result['genuine_previous_tle']).element_epoch_utc_ns()[0]
    assert initial > repaired
    assert result['genuine_previous_receipt']['rejected_near_duplicate_norads'] == [44714]
    assert result['genuine_previous_receipt']['minimum_epoch_separation_s'] == 1.


def test_cached_parsing_keeps_collection_provenance_and_read_checks(monkeypatch):
    cutoff, reader, reads = fixture(monkeypatch, [(-3000, 231.9), (-2000, 232.5),
                                                (-1000, 232.5)])
    original = prepare(reader, cutoff)
    reads.clear()
    parser = ElementParser()
    actual = inputs.prepare_initial_sky(reader, [dict(times=[0., 250.])],
        dict(causal_cutoff_utc_ns=cutoff, anchor_utc_ns=cutoff),
        screen_latitude_deg=10., screen_longitude_deg=20., element_parser=parser)
    assert actual == original
    assert len(reads) == 8  # Three catalogue, three previous, two genuine previous reads.
    assert parser.misses == 2 and parser.hits == 6
    assert actual['nominal_elements']['44714']['provenance']['collected_utc_ns'] == cutoff-1000


@pytest.mark.parametrize('fault', ['future_collection', 'future_bytes', 'wrong_epoch'])
def test_element_bytes_and_provenance_must_both_be_valid(fault):
    cat = parse_element_sets(at_day(232))
    epoch = cat.element_epoch_utc_ns()[0]
    record = dict(lines=list(export_tle(cat.satellites[0])),
                  provenance=dict(element_epoch_utc_ns=epoch, collected_utc_ns=epoch))
    cutoff = epoch + 1000
    if fault == 'future_collection':
        record['provenance']['collected_utc_ns'] = cutoff + 1
    elif fault == 'future_bytes':
        record['lines'] = list(export_tle(parse_element_sets(at_day(234)).satellites[0]))
    else:
        record['provenance']['element_epoch_utc_ns'] -= 1_000_000
    with pytest.raises(ValueError):
        inputs.validate_elements(record, cutoff)
