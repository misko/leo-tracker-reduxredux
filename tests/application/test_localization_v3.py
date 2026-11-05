import pytest

from leo.analysis.polynomial_tracklets import TrackConfig
from leo.application import localization_v3 as app
from tests.analysis.test_localization_v3_tracks import native_document


def test_additional_recovery_keeps_incomplete_inputs_out_of_screening():
    result = app.prepare_additional_recovery(dict(status='cavity_incomplete'), {}, {},
        arms={}, owners={}, identities=[])
    assert result['status'] == 'cavity_incomplete'
    assert result['residual_context'] is None and result['preflight'] is None
    assert not result['recovery_complete']


def test_additional_recovery_passes_full_selected_likelihood_and_native_evidence(monkeypatch):
    original, reconstructed = object(), object()
    native = dict(tracks=['original graph'], observations=['native points'])
    evidence = dict(inventory={'original': True})
    arms, owners = {'selected': 'arms'}, {'selected': 'owners'}
    selection, annotations, receipt = {'kind': 'new_family'}, ['annotation'], {'origin': 123}

    def replay(context, supplied_arms, supplied_owners, **kwargs):
        assert context is original and supplied_arms is arms and supplied_owners is owners
        assert kwargs['selection'] is selection and kwargs['annotations'] is annotations
        assert kwargs['inventory'] is evidence['inventory']
        assert kwargs['observations'] is native['observations']
        return reconstructed

    def rank(tracks, observations, selected_owners, identities):
        assert tracks is native['tracks'] and observations is native['observations']
        assert selected_owners is owners and identities == ['scan']
        return dict(targets=['remaining fragment'])

    def prepare(context, targets, metadata):
        assert context is reconstructed and targets == ['remaining fragment']
        assert metadata is receipt
        return {'corrected': True}

    monkeypatch.setattr(app, 'reconstruct_incumbent', replay)
    monkeypatch.setattr(app, 'rank_targets', rank)
    monkeypatch.setattr(app, 'preflight', prepare)
    result = app.prepare_additional_recovery(dict(status='track_recovery_prepared',
        recovery_context=original, inventory=evidence), native, receipt,
        arms=arms, owners=owners, identities=['scan'], selection=selection,
        annotations=annotations)
    assert result['status'] == 'additional_recovery_prepared'
    assert result['preflight'] == {'corrected': True}
    assert not result['recovery_complete']


def test_recovery_inventory_keeps_incomplete_cavity_out_of_recovery():
    result = app.prepare_track_recovery({}, {}, dict(cavity_fit=None), identities=['scan'])
    assert result['status'] == 'cavity_incomplete' and not result['recovery_complete']


def test_annotation_returns_no_position_inclusion_authority(monkeypatch):
    context, inventory, target = object(), object(), dict(track_id='track', inactive_fragment=True)
    def annotate(actual, inv, tid, **kwargs):
        assert actual is context and inv is inventory and tid == 'track'
        assert kwargs['inactive_fragment'] is True
        return dict(result=dict(no_accepted_associations=True))
    monkeypatch.setattr(app,'annotate',annotate)
    result = app.annotate_recovery_target(dict(status='track_recovery_prepared',
        recovery_context=context,inventory=dict(inventory=inventory)),target)
    assert result['annotation']['result']['no_accepted_associations']
    assert not result['recovery_complete']


def test_recovery_inventory_receives_owned_scan_and_native_points(monkeypatch):
    scan, observations, cavity = object(), [], dict(status='complete')
    def prepare(actual_scan, selected, points, *, identities):
        assert actual_scan is scan and selected is cavity and points is observations
        assert identities == ['source']
        return {'context':True}, {'selected_targets':[]}
    monkeypatch.setattr(app, 'prepare_recovery', prepare)
    result = app.prepare_track_recovery(dict(tracks=dict(observations=observations)),
        dict(signed_context=dict(scan=scan)), dict(cavity_fit=cavity), identities=['source'])
    assert result['status'] == 'track_recovery_prepared' and not result['recovery_complete']


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


def test_cavity_application_uses_owned_context_and_does_not_claim_recovery_completion(monkeypatch):
    context = dict(case='SCAN')
    nomination = dict(status='complete', families=[])
    def nominate(d):
        assert d is context
        return nomination
    def select(d, n):
        assert d is context and n is nomination
        return dict(status='complete', accepted=False)
    monkeypatch.setattr(app, 'nominate_families', nominate)
    monkeypatch.setattr(app, 'cavity_policy', select)
    result = app.fit_family_cavity(dict(status='signed_policy_evaluated', signed_context=context))
    assert result['cavity_fit']['accepted'] is False and result['nominations'] is nomination
    assert result['recovery_complete'] is False
    assert app.fit_family_cavity(dict(status='no_active_curvature')) == dict(
        status='no_active_curvature', nominations=None, cavity_fit=None, recovery_complete=False)


def test_inclusion_application_passes_protected_support_without_mutating_inventory(monkeypatch):
    context, annotation = object(), object()
    evidence = dict(inventory=dict(policy={}), publication_support=dict(c0='protected'))
    prepared = dict(recovery_context=context, inventory=evidence)

    def include(d, inv, a):
        assert d is context and a is annotation
        assert inv['publication_support'] is evidence['publication_support']
        return dict(status='qualified_candidate')

    monkeypatch.setattr(app, 'include_annotation', include)
    result = app.include_recovery_target(prepared,
        dict(status='predictive_annotation_evaluated', annotation=annotation))
    assert result['inclusion']['status'] == 'qualified_candidate'
    assert result['recovery_complete'] is False
    assert 'publication_support' not in evidence['inventory']
    assert app.include_recovery_target({}, dict(status='cavity_incomplete')) == dict(
        status='cavity_incomplete', inclusion=None, recovery_complete=False)


def test_recovery_application_keeps_caller_admission_and_later_policies_explicit(monkeypatch):
    context, evidence, stage, admission = object(), object(), object(), object()
    def recover(d, e, *, run_stage, discovery_allowed):
        assert d is context and e is evidence
        assert run_stage is stage and discovery_allowed is admission
        return dict(decision='ALGO03_single')
    monkeypatch.setattr(app, 'recover_tracks', recover)
    result = app.recover_predictive_tracks(dict(status='track_recovery_prepared',
        recovery_context=context, inventory=evidence), run_stage=stage, discovery_allowed=admission)
    assert result['recovery']['decision'] == 'ALGO03_single'
    assert result['recovery_complete'] is False


def test_predictive_checkpoint_keeps_only_completed_stages_and_inventory_duration(monkeypatch):
    values = iter([1., 4., 7.])

    def recover(d, e, *, run_stage, discovery_allowed):
        assert run_stage('done', lambda: {'scientific': True}) == (True, {'scientific': True})
        assert run_stage('failed', lambda: None) == (False, None)
        return dict(selected=None)

    monkeypatch.setattr(app, 'recover_tracks', recover)
    prepared = dict(status='track_recovery_prepared', recovery_context={}, inventory={})
    result = app.recover_predictive_checkpoint(prepared,
        run_stage=lambda name, operation: (True, operation()) if name == 'done' else (False, None),
        discovery_allowed=lambda: True, clock=lambda: next(values), inventory_seconds=2.)
    assert set(result['completed_stages']) == {'inventory', 'done'}
    assert result['completed_stages']['done']['seconds'] == 3.
    assert result['completed_stages']['inventory']['seconds'] == 2.
    assert result['recovery_complete'] is False


def test_numerical_application_uses_owned_checkpoint_and_retains_future_policy_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr(app, 'replay_recovery', lambda *a, **kw: calls.append((a, kw)) or
                        dict(decision='ALGO03_fallback'))
    prepared = dict(recovery_context='owned', inventory='evidence')
    predictive = dict(status='predictive_recovery_evaluated', recovery='incumbent', completed_stages='records')
    ports = dict(run_stage='stage', discovery_allowed='admission', clock='clock', charge_reused='charge')
    result = app.recover_numerical_tracks(prepared, predictive, **ports)
    assert calls == [(('owned', 'evidence', 'incumbent', 'records'), ports)]
    assert result['status'] == 'numerical_recovery_evaluated'
    assert result['recovery_complete'] is False


def test_numerical_checkpoint_keeps_completed_annotations_even_when_selection_falls_back(monkeypatch):
    annotation = dict(result=dict(track_id='rejected-parent'))

    def replay(*args, run_stage, **kwargs):
        run_stage('target-0-annotation', lambda: annotation)
        run_stage('target-0-inclusion', lambda: 'failed-fit')
        return dict(decision='ALGO03_fallback')

    monkeypatch.setattr(app, 'replay_recovery', replay)
    result = app.recover_numerical_checkpoint(
        dict(recovery_context={}, inventory={}),
        dict(status='predictive_recovery_evaluated', recovery={}, completed_stages={}),
        run_stage=lambda name, operation: (True, operation()) if name.endswith('annotation') else (False, None),
        discovery_allowed=lambda: True, clock=lambda: 0., charge_reused=lambda _: None)
    assert result['completed_stages'] == {'target-0-annotation': annotation}
    assert result['recovery']['decision'] == 'ALGO03_fallback'


def test_gap_application_uses_numerical_rejections_and_actually_selected_owners(monkeypatch):
    calls = []
    monkeypatch.setattr(app, 'recover_gaps', lambda *a, **kw: calls.append((a, kw)) or dict(candidate=None))
    original = {arm: dict(owners={'original': 1}) for arm in ('c0', 'fitted_c')}
    selected = {arm: dict(owners={'original': 1, 'retained': 2}) for arm in ('c0', 'fitted_c')}
    annotation = dict(result=dict(track_id='parent'))
    attempts = dict(attempts=['numerical-attempt'])
    previous = dict(candidate=attempts, retained=dict(source_support=original, attempts=[]),
                    selected=dict(arms=selected))
    numerical = dict(status='numerical_recovery_evaluated', recovery=previous,
                     completed_stages={'target-0-annotation': annotation, 'target-0-audit': {}})
    prepared = dict(recovery_context='owned-context', inventory=dict(
        inventory=dict(policy='original-calibration'), publication_support=original))
    ports = dict(run_stage='stage', clock='clock', maximum_seconds=900)
    result = app.recover_gap_tracks(prepared, numerical, 'native-points', **ports)
    args, kwargs = calls.pop()
    assert args == ('owned-context', dict(policy='original-calibration', publication_support=original),
                    'native-points', attempts, {'parent': annotation},
                    {arm: selected[arm]['owners'] for arm in selected})
    assert kwargs == ports
    assert result['incumbent'] is previous
    assert result['status'] == 'gap_recovery_evaluated' and not result['recovery_complete']
    previous['selected'] = None
    app.recover_gap_tracks(prepared, numerical, 'native-points', **ports)
    assert calls[0][0][-1] == {arm: original[arm]['owners'] for arm in original}


def test_gap_application_reports_missing_numerical_checkpoint_without_fabricating_attempts(monkeypatch):
    monkeypatch.setattr(app, 'recover_gaps', lambda *a, **kw: pytest.fail('no source attempts'))
    previous = dict(candidate=dict(failure='inventory failed'))
    result = app.recover_gap_tracks({},
        dict(status='numerical_recovery_evaluated', recovery=previous), [],
        run_stage=None, clock=None)
    assert result['status'] == 'gap_source_incomplete'
    assert result['incumbent'] is previous and result['recovery'] is None
