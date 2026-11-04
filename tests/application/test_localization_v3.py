import pytest

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application import localization_v3 as app
from tests.analysis.test_localization_v3_tracks import native_document


def test_no_curvature_does_not_read_archive():
    document = native_document()
    for probe in document['source']['probes']:
        probe['candidates'][0]['passed_fractional_margin_gate'] = False
    result = app.prepare_native_scan(document, None, TrackConfig(),
                                     screen_latitude_deg=10., screen_longitude_deg=20.)
    assert result['status'] == 'no_active_curvature'
    assert result['sky'] is None


def test_native_clock_and_tracks_are_the_only_sky_preparation_inputs(monkeypatch):
    archive = object()
    parsers = []

    def sky(reader, tracks, metadata, **kwargs):
        assert reader is archive
        assert len(tracks) == 2
        assert metadata['causal_cutoff_utc_ns'] == 1_000_000_000
        parsers.append(kwargs.pop('element_parser'))
        assert kwargs == dict(screen_latitude_deg=10., screen_longitude_deg=20.)
        return dict(marker='prepared', nominal_elements={})

    def history(archive, elements, metadata, *, element_parser):
        assert element_parser is parsers[0]
        return dict(case='SCAN', cutoff_utc_ns=metadata['causal_cutoff_utc_ns'], past_versions={})

    monkeypatch.setattr(app, 'prepare_initial_sky', sky)
    monkeypatch.setattr(app, 'prepare_phase_history', history)
    result = app.prepare_native_scan(native_document(), archive, TrackConfig(),
                                     screen_latitude_deg=10., screen_longitude_deg=20.)
    assert result['status'] == 'inputs_prepared'
    assert result['sky'] == dict(marker='prepared', nominal_elements={})
    assert result['phase_forecast']['all_past_distribution']['fallback']
    assert 'position' not in result


def test_archive_failure_does_not_become_a_position_fallback(monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError('missing causal history')

    monkeypatch.setattr(app, 'prepare_initial_sky', fail)
    with pytest.raises(ValueError, match='missing causal history'):
        app.prepare_native_scan(native_document(), None, TrackConfig(),
                                 screen_latitude_deg=10., screen_longitude_deg=20.)
