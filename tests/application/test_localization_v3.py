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


def test_initial_fit_preserves_prior_stage_and_does_not_claim_final_completion(monkeypatch):
    from types import SimpleNamespace

    from leo.analysis.localization_v3.region import SearchRegion

    region = SearchRegion((10., 20.))
    prepared = dict(status='inputs_prepared', tracks=dict(tracks=[]), noise={'sigma': 150.},
        sky=dict(bank={}, nominal_elements={}, previous_tle='original previous',
                 genuine_previous_tle='later repaired previous',
                 previous_receipt=dict(catalogue_sha256='bound previous'),
                 metadata=dict(origin_utc_ns=123, regional_center=[1., 2.])))
    marker = object()

    def make_scan(tracks, bank, elements, **kwargs):
        assert kwargs['previous_tle'] == 'original previous'
        assert kwargs['previous_tle_sha256'] == 'bound previous'
        assert kwargs['search_region'] is region
        assert kwargs['regional_center'] == [1., 2.]
        assert kwargs['noise'] is prepared['noise']
        return SimpleNamespace(radio_sigma_hz=150.)

    def search(scan, sigma, **kwargs):
        # No reduced/default overrides at the application entry point.
        assert kwargs == {'on_branch': marker}
        return dict(selected_hypothesis=2)

    monkeypatch.setattr(app, 'ScanLikelihood', make_scan)
    monkeypatch.setattr(app, 'initial_search', search)
    result = app.fit_initial_position(prepared, region, on_branch=marker)
    assert result == dict(status='initial_position_fitted',
                         initial_fit={'selected_hypothesis': 2}, recovery_complete=False)
    assert app.fit_initial_position({'status': 'no_active_curvature'}, region) == dict(
        status='no_active_curvature', initial_fit=None, recovery_complete=False)


def test_refit_constructs_a_fresh_context_with_genuine_previous_prior(monkeypatch):
    from types import SimpleNamespace

    observation = dict(observation_id='native-1')
    prepared = dict(status='inputs_prepared', tracks=dict(tracks=[], observations=[observation]),
        noise={}, sky=dict(bank={}, nominal_elements={}, previous_tle='initial',
        genuine_previous_tle='genuine', genuine_previous_receipt=dict(
            catalogue_sha256='genuine-sha', sources={'1': {'epoch_utc_ns': 5}}),
        metadata=dict(origin_utc_ns=10, regional_center=[1., 2.])))
    initial, region, contexts = {}, object(), []

    def context(*args, **kw):
        assert kw['previous_tle'] == 'genuine'
        assert kw['previous_tle_sha256'] == 'genuine-sha'
        assert kw['previous_sources'] == {'1': {'epoch_utc_ns': 5}}
        result = SimpleNamespace()
        contexts.append(result)
        return result

    def recovery(scan, result, observations, **kwargs):
        assert scan is contexts[-1] and result is initial
        assert observations == [observation] and kwargs == dict(on_round=None)
        return dict(status='gate_refit_unstable')

    monkeypatch.setattr(app, 'ScanLikelihood', context)
    monkeypatch.setattr(app, 'conservative_recovery', recovery)
    result = app.refit_initial_position(prepared, initial, region)
    assert result['conservative_fit']['status'] == 'gate_refit_unstable'
    assert result['recovery_complete'] is False
    app.refit_initial_position(prepared, initial, region)
    assert contexts[0] is not contexts[1]


def test_family_policy_binds_owned_history_without_mutating_forecast(monkeypatch):
    import hashlib
    import json

    prepared = dict(status='inputs_prepared', phase_history=dict(case='SCAN'),
                    phase_forecast=dict(strictly_pre_RF=True),
                    sky=dict(metadata=dict(cutoff_utc_ns=90)))
    scan, conservative, region = object(), {}, object()

    def context(p, r, noise, *, genuine):
        assert p is prepared and r is region and genuine
        return scan

    def policy(s, c, raw, forecast, **kwargs):
        assert s is scan and c is conservative and raw is prepared['phase_history']
        digest = hashlib.sha256((json.dumps(raw, sort_keys=True)+'\n').encode()).hexdigest()
        assert kwargs == dict(case='SCAN', cutoff_utc_ns=90, history_sha256=digest)
        assert forecast['history_sha256'] == digest
        return dict(status='accepted', fallback='curved_pair')

    monkeypatch.setattr(app, '_context', context)
    monkeypatch.setattr(app, 'history_policy', policy)
    result = app.fit_family_policy(prepared, conservative, region)
    assert result['family_fit']['fallback'] == 'curved_pair'
    assert result['recovery_complete'] is False
    assert 'history_sha256' not in prepared['phase_forecast']
    prepared['phase_forecast']['history_sha256'] = 'different'
    with pytest.raises(ValueError, match='binding'):
        app.fit_family_policy(prepared, conservative, region)


def test_signed_application_binds_native_inputs_and_keeps_later_recovery_open(monkeypatch):
    import hashlib
    import json

    prepared = dict(status='inputs_prepared', phase_history=dict(case='SCAN'),
        phase_forecast={}, sky=dict(metadata=dict(cutoff_utc_ns=90)),
        tracks=dict(observations=['native']))
    region, scan, conservative, family = object(), object(), {}, {}
    def context(p, r, noise, *, genuine):
        assert p is prepared and r is region and genuine
        return scan
    def policy(s, c, f, raw, forecast, observations, **kwargs):
        assert s is scan and c is conservative and f is family
        assert observations is prepared['tracks']['observations']
        assert raw is prepared['phase_history']
        digest = hashlib.sha256((json.dumps(raw, sort_keys=True)+'\n').encode()).hexdigest()
        assert forecast['history_sha256'] == digest
        assert kwargs == dict(case='SCAN', cutoff_utc_ns=90, history_sha256=digest)
        return dict(signed=dict(accepted=False))
    monkeypatch.setattr(app, '_context', context)
    monkeypatch.setattr(app, 'signed_context', policy)
    result = app.fit_signed_policy(prepared, conservative, family, region)
    assert result['signed_context']['signed']['accepted'] is False
    assert result['recovery_complete'] is False
    assert prepared['phase_forecast'] == {}
    assert app.fit_signed_policy(dict(status='no_active_curvature'), {}, {}, region) == dict(
        status='no_active_curvature', signed_context=None, recovery_complete=False)
