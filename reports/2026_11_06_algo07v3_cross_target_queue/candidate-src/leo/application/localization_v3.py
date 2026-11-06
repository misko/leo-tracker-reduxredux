"""Standalone preparation and initial regional position search.

No earlier ALGO jobs or result stores are inputs. Initial, conservative and
family/history, signed-prior and family-cavity fitting are included; later
ordered recovery remains unfinished.
"""
import hashlib
import json

from leo.analysis.localization_v3.conservative_recovery import conservative_recovery
from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.family_cavity import cavity_policy, nominate_families
from leo.analysis.localization_v3.gap_controller import recover_gaps
from leo.analysis.localization_v3.history_policy import history_policy
from leo.analysis.localization_v3.initial_search import initial_search
from leo.analysis.localization_v3.noise import estimate_noise
from leo.analysis.localization_v3.numerical_recovery import replay_recovery
from leo.analysis.localization_v3.phase_prior import forecast
from leo.analysis.localization_v3.predictive_annotation import annotate
from leo.analysis.localization_v3.recovery_controller import recover_tracks
from leo.analysis.localization_v3.recovery_inclusion import include_annotation
from leo.analysis.localization_v3.recovery_inventory import prepare_recovery
from leo.analysis.localization_v3.residual_preflight import preflight, rank_targets
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent
from leo.analysis.localization_v3.signed_context import signed_context
from leo.analysis.localization_v3.tracks import prepare_tracks


def prepare_initial_sky(*args, **kwargs):
    """Load the owned archive adapter only at the input-preparation boundary."""
    from leo.operations.localization_v3_inputs import prepare_initial_sky as prepare
    return prepare(*args, **kwargs)


def prepare_phase_history(*args, **kwargs):
    """Fitting an already prepared scan does not import operational adapters."""
    from leo.operations.localization_v3_inputs import prepare_phase_history as prepare
    return prepare(*args, **kwargs)


def prepare_native_scan(document, archive, track_config, *,
                        screen_latitude_deg, screen_longitude_deg, element_parser=None):
    prepared = prepare_tracks(document, track_config)
    if prepared['status'] != 'tracks_prepared':
        return dict(status=prepared['status'], tracks=prepared, sky=None)
    if element_parser is None:
        element_parser = ElementParser()
    sky = prepare_initial_sky(archive, prepared['tracks'], prepared['metadata'],
                              element_parser=element_parser,
                              screen_latitude_deg=screen_latitude_deg,
                              screen_longitude_deg=screen_longitude_deg)
    noise = estimate_noise(prepared['tracks'], prepared['observations'])
    history = prepare_phase_history(archive, sky['nominal_elements'], prepared['metadata'],
                                    element_parser=element_parser)
    return dict(status='inputs_prepared', tracks=prepared, sky=sky, noise=noise,
                phase_history=history, phase_forecast=forecast(history))


def fit_initial_position(prepared, search_region, *, noise_sha256=None, on_branch=None,
                         map_arms=None, map_branches=None):
    """Run the original full initial-search budgets on native prepared evidence.

    Use the original previous-orbit prior at this stage. The separately prepared
    genuine-previous prior and phase forecast belong to later fitting policies.
    This result is an initial incumbent, never a completed ALGO07 publication.
    """
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], initial_fit=None, recovery_complete=False)
    scan = _context(prepared, search_region, noise_sha256, genuine=False)
    execution = {} if map_arms is None else dict(map_arms=map_arms)
    if map_branches is not None:
        execution['map_branches'] = map_branches
    result = initial_search(scan, scan.radio_sigma_hz, on_branch=on_branch, **execution)
    return dict(status='initial_position_fitted', initial_fit=result, recovery_complete=False)


def refit_initial_position(prepared, initial, search_region, *, noise_sha256=None, on_round=None,
                           map_arms=None):
    """Use a fresh context for the genuine-previous prior and conservative recovery.

    Later ordered recovery policies remain separate from this incumbent.
    """
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], conservative_fit=None, recovery_complete=False)
    scan = _context(prepared, search_region, noise_sha256, genuine=True)
    result = conservative_recovery(scan, initial, prepared['tracks']['observations'],
                                    on_round=on_round,
                                    **({'map_arms': map_arms} if map_arms is not None else {}))
    return dict(status='conservative_fit_evaluated', conservative_fit=result,
                recovery_complete=False)


def _context(prepared, search_region, noise_sha256, *, genuine):
    sky = prepared['sky']
    prefix = 'genuine_previous' if genuine else 'previous'
    receipt = sky[prefix+'_receipt']
    return ScanLikelihood(prepared['tracks']['tracks'], sky['bank'], sky['nominal_elements'],
        origin_utc_ns=sky['metadata']['origin_utc_ns'],
        regional_center=sky['metadata']['regional_center'], noise=prepared['noise'],
        noise_sha256=noise_sha256, search_region=search_region,
        previous_tle=sky[prefix+'_tle'], previous_tle_sha256=receipt['catalogue_sha256'],
        previous_sources=receipt['sources'] if genuine else receipt.get('sources'))


def fit_family_policy(prepared, conservative, search_region, *, noise_sha256=None, map_arms=None):
    """Bind owned in-memory history and evaluate the original paired family policy."""
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], family_fit=None, recovery_complete=False)
    history, phase_forecast, history_sha256 = _bound_history(prepared)
    scan = _context(prepared, search_region, noise_sha256, genuine=True)
    result = history_policy(scan, conservative, history, phase_forecast,
        case='SCAN', cutoff_utc_ns=prepared['sky']['metadata']['cutoff_utc_ns'],
        history_sha256=history_sha256, **({'map_arms': map_arms} if map_arms is not None else {}))
    return dict(status='family_policy_evaluated', family_fit=result, recovery_complete=False)


def _bound_history(prepared):
    history = prepared['phase_history']
    history_bytes = (json.dumps(history, sort_keys=True, allow_nan=False)+'\n').encode()
    history_sha256 = hashlib.sha256(history_bytes).hexdigest()
    if prepared['phase_forecast'].get('history_sha256', history_sha256) != history_sha256:
        raise ValueError('In-memory phase forecast/history binding differs')
    phase_forecast = dict(prepared['phase_forecast'], history_sha256=history_sha256)
    return history, phase_forecast, history_sha256


def fit_signed_policy(prepared, conservative, family, search_region, *, noise_sha256=None):
    """Prepare the signed-prior numerical context for subsequent cavity selection."""
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], signed_context=None, recovery_complete=False)
    history, phase_forecast, history_sha256 = _bound_history(prepared)
    scan = _context(prepared, search_region, noise_sha256, genuine=True)
    result = signed_context(scan, conservative, family, history, phase_forecast,
        prepared['tracks']['observations'],
        case='SCAN', cutoff_utc_ns=prepared['sky']['metadata']['cutoff_utc_ns'],
        history_sha256=history_sha256)
    return dict(status='signed_policy_evaluated', signed_context=result, recovery_complete=False)


def fit_family_cavity(signed):
    """Nominate and fit complete-family alternatives from the owned signed context."""
    if signed['status'] != 'signed_policy_evaluated':
        return dict(status=signed['status'], nominations=None, cavity_fit=None,
                    recovery_complete=False)
    context = signed['signed_context']
    nominations = nominate_families(context)
    result = cavity_policy(context, nominations)
    return dict(status='family_cavity_evaluated', nominations=nominations, cavity_fit=result,
                recovery_complete=False)


def prepare_track_recovery(prepared, signed, cavity, *, identities):
    """Replay the selected policy and identify the original recovery targets."""
    if (cavity.get('cavity_fit') or {}).get('status') != 'complete':
        return dict(status='cavity_incomplete', recovery_context=None, inventory=None,
                    recovery_complete=False)
    context, result = prepare_recovery(signed['signed_context']['scan'], cavity['cavity_fit'],
        prepared['tracks']['observations'], identities=identities)
    return dict(status='track_recovery_prepared', recovery_context=context, inventory=result,
                recovery_complete=False)


def annotate_recovery_target(prepared_recovery, target, *, on_proposal=None):
    """Test a nominated curve predictively; do not authorize position inclusion."""
    if prepared_recovery['status'] != 'track_recovery_prepared':
        return dict(status=prepared_recovery['status'], annotation=None, recovery_complete=False)
    result = annotate(prepared_recovery['recovery_context'],
        prepared_recovery['inventory']['inventory'], target['track_id'],
        inactive_fragment=target['inactive_fragment'], on_proposal=on_proposal)
    return dict(status='predictive_annotation_evaluated', annotation=result,
                recovery_complete=False)


def include_recovery_target(prepared_recovery, annotated):
    """Evaluate one candidate addition; full ordered recovery remains separate."""
    if annotated['status'] != 'predictive_annotation_evaluated':
        return dict(status=annotated['status'], inclusion=None, recovery_complete=False)
    evidence = prepared_recovery['inventory']
    inventory = dict(evidence['inventory'], publication_support=evidence['publication_support'])
    result = include_annotation(prepared_recovery['recovery_context'],inventory,
                                annotated['annotation'])
    return dict(status='predictive_inclusion_evaluated', inclusion=result, recovery_complete=False)


def recover_predictive_tracks(prepared_recovery, *, run_stage, discovery_allowed,
                              on_selection=None, map_annotation_folds=None,
                              map_inclusion_arms=None, map_annotation_training=None,
                              map_all_target_training=None):
    """Run ordered recovery with explicit caller-owned admission and execution."""
    if prepared_recovery['status'] != 'track_recovery_prepared':
        return dict(status=prepared_recovery['status'], recovery=None, recovery_complete=False)
    result = recover_tracks(prepared_recovery['recovery_context'], prepared_recovery['inventory'],
                            run_stage=run_stage, discovery_allowed=discovery_allowed,
                            **({'map_annotation_folds': map_annotation_folds}
                               if map_annotation_folds else {}),
                            **({'map_inclusion_arms': map_inclusion_arms}
                               if map_inclusion_arms else {}),
                            **({'map_annotation_training': map_annotation_training}
                               if map_annotation_training else {}),
                            **({'map_all_target_training': map_all_target_training}
                               if map_all_target_training else {}),
                            **({'on_selection': on_selection} if on_selection is not None else {}))
    return dict(status='predictive_recovery_evaluated', recovery=result, recovery_complete=False)


def recover_predictive_checkpoint(prepared_recovery, *, run_stage, discovery_allowed, clock,
                                  inventory_seconds, map_annotation_folds=None,
                                  map_inclusion_arms=None, map_annotation_training=None,
                                  map_all_target_training=None):
    """Keep owned stage values for the immediately following numerical policy."""
    completed = {'inventory': dict(value=prepared_recovery['inventory'], seconds=inventory_seconds)}
    selection = []

    def captured(name, operation):
        began = clock()
        ok, value = run_stage(name, operation)
        if ok:
            completed[name] = dict(value=value, seconds=clock() - began)
        return ok, value

    result = recover_predictive_tracks(prepared_recovery, run_stage=captured,
                                      discovery_allowed=discovery_allowed,
                                      on_selection=selection.append,
                                      **({'map_inclusion_arms': map_inclusion_arms}
                                         if map_inclusion_arms else {}),
                                      **({'map_annotation_folds': map_annotation_folds}
                                         if map_annotation_folds else {}),
                                      **({'map_annotation_training': map_annotation_training}
                                         if map_annotation_training else {}),
                                      **({'map_all_target_training': map_all_target_training}
                                         if map_all_target_training else {}))
    return dict(result, completed_stages=completed,
                selected_state=selection[0] if selection else None)


def recover_numerical_tracks(prepared_recovery, predictive, *, run_stage,
                             discovery_allowed, clock, charge_reused, on_selection=None,
                             map_inclusion_arms=None):
    """Replay the owned checkpoint and retain the exact incumbent on rejection."""
    if predictive['status'] != 'predictive_recovery_evaluated':
        return dict(status=predictive['status'], recovery=None, recovery_complete=False)
    result = replay_recovery(prepared_recovery['recovery_context'], prepared_recovery['inventory'],
        predictive['recovery'], predictive['completed_stages'], run_stage=run_stage,
        discovery_allowed=discovery_allowed, clock=clock, charge_reused=charge_reused,
        **({'map_inclusion_arms': map_inclusion_arms} if map_inclusion_arms else {}),
        **({'on_selection': on_selection} if on_selection is not None else {}))
    return dict(status='numerical_recovery_evaluated', recovery=result, recovery_complete=False)


def recover_numerical_checkpoint(prepared_recovery, predictive, *, run_stage,
                                 discovery_allowed, clock, charge_reused,
                                 map_inclusion_arms=None):
    """Retain completed numerical annotations, including on incumbent fallback."""
    completed = {}
    selection = []

    def captured(name, operation):
        ok, value = run_stage(name, operation)
        if ok:
            completed[name] = value
        return ok, value

    result = recover_numerical_tracks(prepared_recovery, predictive, run_stage=captured,
        discovery_allowed=discovery_allowed, clock=clock, charge_reused=charge_reused,
        on_selection=selection.append,
        **({'map_inclusion_arms': map_inclusion_arms} if map_inclusion_arms else {}))
    return dict(result, completed_stages=completed,
                selected_state=selection[0] if selection else predictive.get('selected_state'))


def recover_gap_tracks(prepared_recovery, numerical, observations, *, run_stage, clock,
                       maximum_seconds=1200, on_selection=None):
    """Use numerical attempts but protect owners of the actually adopted fit.

    This is an owned scientific checkpoint, not a published legacy terminal.
    Final proof validation and later recovery/publication remain separate.
    """
    if numerical['status'] != 'numerical_recovery_evaluated':
        return dict(status=numerical['status'], recovery=None, recovery_complete=False)
    previous = numerical['recovery']
    if 'attempts' not in previous['candidate']:
        return dict(status='gap_source_incomplete', recovery=None, incumbent=previous,
                    recovery_complete=False)
    support = (previous['selected']['arms'] if previous.get('selected')
               else previous['retained']['source_support'])
    owners = {arm: support[arm]['owners'] for arm in ('c0', 'fitted_c')}
    annotations = {value['result']['track_id']: value
                   for name, value in numerical['completed_stages'].items()
                   if name.endswith('-annotation')}
    evidence = prepared_recovery['inventory']
    inventory = dict(evidence['inventory'], publication_support=evidence['publication_support'])
    result = recover_gaps(prepared_recovery['recovery_context'], inventory, observations,
        previous['candidate'], annotations, owners, run_stage=run_stage, clock=clock,
        maximum_seconds=maximum_seconds,
        **({'on_selection': on_selection} if on_selection is not None else {}))
    return dict(status='gap_recovery_evaluated', recovery=result, incumbent=previous,
                recovery_complete=False)


def recover_gap_checkpoint(prepared_recovery, numerical, observations, *, run_stage, clock,
                           maximum_seconds=1200):
    """Keep the chosen gap likelihood; rejection retains the numerical incumbent."""
    selection = []
    result = recover_gap_tracks(prepared_recovery, numerical, observations, run_stage=run_stage,
        clock=clock, maximum_seconds=maximum_seconds, on_selection=selection.append)
    return dict(result,
                selected_state=selection[0] if selection else numerical.get('selected_state'))


def prepare_additional_checkpoint(prepared_recovery, native, scan_receipt, checkpoint, *,
                                  identities):
    """Bind the selected owned likelihood to the separately retained scientific proof."""
    if checkpoint['status'] != 'gap_recovery_evaluated':
        return dict(status=checkpoint['status'], residual_context=None,
                    residual_inventory=None, preflight=None, recovery_complete=False)
    state = checkpoint.get('selected_state')
    if state is None:
        raise ValueError('Selected likelihood checkpoint missing')
    gaps, previous = checkpoint['recovery'], checkpoint['incumbent']
    if gaps['candidate'] is not None:
        expected = gaps['candidate']['trial']['arms']
        expected_owners = {a: r['proposed_owners'] for a, r in expected.items()}
        kind = 'gap_conditional'
    elif previous.get('selected'):
        expected = previous['selected']['arms']
        expected_owners = {a: r['owners'] for a, r in expected.items()}
        kind = previous['selected']['kind']
    else:
        expected = prepared_recovery['inventory']['inventory']['policy']
        expected_owners = {a: r['owners']
                           for a, r in previous['retained']['source_support'].items()}
        kind = None
    if state['owners'] != expected_owners or (
        state['selection']['kind'] if state['selection'] else None) != kind:
        raise ValueError('Selected likelihood does not bind to the adopted ownership/kind')
    for arm in ('c0', 'fitted_c'):
        for key in ('endpoint_latlon', 'endpoint_east_north_km', 'negative_twice_elbo'):
            if (key in expected[arm] and _selected_value(state['arms'][arm][key])
                    != _selected_value(expected[arm][key])):
                raise ValueError('Selected likelihood does not bind to the adopted ' + key)
    if kind == 'gap_conditional' and previous.get('selected'):
        raise ValueError('Gap over separately recovered family requires explicit composition')
    return prepare_additional_recovery(prepared_recovery, native, scan_receipt,
        arms=state['arms'], owners=state['owners'], identities=identities,
        selection=state['selection'], annotations=state['annotations'])


def _selected_value(value):
    """Compare owned array/list selected endpoint values without tolerance."""
    return value.tolist() if hasattr(value, 'tolist') else value


def prepare_additional_catalogue(archive, cutoff_utc_ns, *, element_parser=None):
    """Read the owned recovery catalogue only at the operational boundary."""
    from leo.operations.localization_v3_inputs import prepare_recovery_catalogue
    return prepare_recovery_catalogue(archive, cutoff_utc_ns,
        **({'element_parser': element_parser} if element_parser is not None else {}))


def screen_additional_recovery(prepared, catalogue, search_region, *, on_target=None):
    """Apply the deployed 72-hour / 30-second screen without a recency penalty."""
    if prepared['status'] != 'additional_recovery_prepared':
        return dict(status=prepared['status'], screen=None, recovery_complete=False)
    from leo.analysis.localization_v3.residual_screen import screen_candidates
    result = screen_candidates(prepared['preflight'], catalogue, search_region,
                               policy='72h_30s', on_target=on_target)
    return dict(status='additional_candidates_screened', screen=result, recovery_complete=False)


def fit_additional_recovery(prepared, screened, catalogue, observations, *, clock, on_arm=None):
    """Fit matched control/addition from the owned selected-state reconstruction.

    This is a qualified conditional trial, not final guarded reassociation or
    publication. No older result directory is an input to the fitting controller.
    """
    if prepared['status'] != 'additional_recovery_prepared':
        return dict(status=prepared['status'], recovery=None, recovery_complete=False)
    if screened['status'] != 'additional_candidates_screened':
        return dict(status=screened['status'], recovery=None, recovery_complete=False)
    packet, screen = prepared['preflight'], screened['screen']
    if (screen['case'] != packet['case'] or
        [t['source'] for t in screen['targets']] != [t['source'] for t in packet['targets']]):
        raise ValueError('Residual screen does not bind to the prepared native targets')
    if catalogue['cutoff_utc_ns'] != packet['scan_receipt']['cutoff_utc_ns']:
        raise ValueError('Residual catalogue cutoff changed after screening')
    from leo.analysis.localization_v3.additional_recovery import recover_additional
    result = recover_additional(prepared['context_factory'], prepared['incumbent_owners'],
        screen, catalogue, observations, family_count=len(prepared['residual_context']['families']),
        policy='72h_30s', clock=clock, on_arm=on_arm)
    return dict(status='additional_position_evaluated', recovery=result, recovery_complete=False)


def prepare_reassociation(prepared, position, screened, catalogue, observations):
    """Restore the exact owned incumbent for final guarded identity repair."""
    for result, status in ((prepared, 'additional_recovery_prepared'),
                           (position, 'additional_position_evaluated'),
                           (screened, 'additional_candidates_screened')):
        if result['status'] != status:
            return dict(status=result['status'], context=None, recovery_complete=False)
    from leo.analysis.localization_v3.reassociation_context import adopt_additional
    result = adopt_additional(prepared['context_factory'], prepared['incumbent_arms'],
        prepared['incumbent_owners'], prepared['incumbent_selection'], position['recovery'],
        screened['screen'], catalogue, observations)
    return dict(result, status='reassociation_prepared', recovery_complete=False)


def rank_reassociation_families(prepared):
    """Run the original top-two RF-influence trigger, without location truth."""
    if prepared['status'] != 'reassociation_prepared':
        return dict(status=prepared['status'], ranking=None, targets=None, recovery_complete=False)
    from leo.analysis.localization_v3.reassociation_context import rank_families
    ranking, targets = rank_families(prepared['context'])
    return dict(status='reassociation_targets_ranked', ranking=ranking, targets=targets,
                recovery_complete=False)


def screen_reassociation_candidates(prepared, ranked, catalogue, scan_receipt, *, on_target=None):
    """Run causal nomination and the primary shared-receiver guard before any refit."""
    for result, status in ((prepared, 'reassociation_prepared'),
                           (ranked, 'reassociation_targets_ranked')):
        if result['status'] != status:
            return dict(status=result['status'], admission=None, recovery_complete=False)
    from leo.analysis.localization_v3.reassociation_admission import admit
    result = admit(prepared['context'], prepared['owners'], ranked['targets'], catalogue,
                   scan_receipt, on_target=on_target)
    return dict(status='reassociation_candidates_screened', admission=result,
                recovery_complete=False)


def fit_reassociation(prepared, screened, catalogue, scan_receipt, collect_history,
                      *, on_fit=None, on_record=None, on_selected=None):
    """Finish matched identity repair; publication remains a separate boundary."""
    for result, status in ((prepared, 'reassociation_prepared'),
                           (screened, 'reassociation_candidates_screened')):
        if result['status'] != status:
            return dict(status=result['status'], recovery=None, recovery_complete=False)
    if catalogue['cutoff_utc_ns'] != scan_receipt['cutoff_utc_ns']:
        raise ValueError('Reassociation catalogue cutoff changed')
    from leo.analysis.localization_v3.reassociation_recovery import baseline_from_selected, recover
    baseline = baseline_from_selected(prepared['arms'], prepared['owners'])
    kwargs = dict(on_fit=on_fit, on_record=on_record)
    if on_selected is not None:
        kwargs['on_selected'] = on_selected
    result = recover(prepared['context'], prepared['owners'], baseline, screened['admission'],
                     catalogue, scan_receipt, collect_history, **kwargs)
    return dict(status='reassociation_evaluated', recovery=result,
                recovery_complete=result['execution_status'] == 'complete')


def prepare_reassociation_history(archive, cutoff_utc_ns):
    """Build the final-stage history bank through the owned read-only archive port."""
    from leo.operations.localization_v3_history import collect_versions
    return collect_versions(archive, cutoff_utc_ns)


def prepare_additional_recovery(prepared_recovery, native, scan_receipt, *,
                                arms, owners, identities, selection=None, annotations=()):
    """Replay an explicitly chosen owned likelihood and rank remaining evidence.

    The caller supplies the selected stage's full scientific data, not a legacy
    terminal or a path. This does not run catalogue screening or accept a new
    association. Selection/checkpoint binding remains the caller's responsibility.
    """
    if prepared_recovery['status'] != 'track_recovery_prepared':
        return dict(status=prepared_recovery['status'], residual_context=None,
                    residual_inventory=None, preflight=None, recovery_complete=False)
    def fresh():
        return reconstruct_incumbent(prepared_recovery['recovery_context'], arms, owners,
            selection=selection, inventory=prepared_recovery['inventory']['inventory'],
            annotations=annotations, observations=native['observations'])
    context = fresh()
    ranked = rank_targets(native['tracks'], native['observations'], owners, identities)
    packet = preflight(context, ranked['targets'], scan_receipt)
    return dict(status='additional_recovery_prepared', residual_context=context,
                residual_inventory=ranked, preflight=packet, recovery_complete=False,
                context_factory=fresh, incumbent_owners=owners, incumbent_arms=arms,
                incumbent_selection=selection)
