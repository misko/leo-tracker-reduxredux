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
from leo.analysis.localization_v3.recovery_inclusion import include_annotation
from leo.analysis.localization_v3.recovery_controller import recover_tracks
from leo.analysis.localization_v3.recovery_inventory import prepare_recovery
from leo.analysis.localization_v3.residual_preflight import preflight, rank_targets
from leo.analysis.localization_v3.selected_incumbent import reconstruct_incumbent
from leo.analysis.localization_v3.scan import ScanLikelihood
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


def fit_initial_position(prepared, search_region, *, noise_sha256=None, on_branch=None):
    """Run the original full initial-search budgets on native prepared evidence.

    Use the original previous-orbit prior at this stage. The separately prepared
    genuine-previous prior and phase forecast belong to later fitting policies.
    This result is an initial incumbent, never a completed ALGO07 publication.
    """
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], initial_fit=None, recovery_complete=False)
    scan = _context(prepared, search_region, noise_sha256, genuine=False)
    result = initial_search(scan, scan.radio_sigma_hz, on_branch=on_branch)
    return dict(status='initial_position_fitted', initial_fit=result, recovery_complete=False)


def refit_initial_position(prepared, initial, search_region, *, noise_sha256=None, on_round=None):
    """Use a fresh context for the genuine-previous prior and conservative recovery.

    Later ordered recovery policies remain separate from this incumbent.
    """
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], conservative_fit=None, recovery_complete=False)
    scan = _context(prepared, search_region, noise_sha256, genuine=True)
    result = conservative_recovery(scan, initial, prepared['tracks']['observations'],
                                    on_round=on_round)
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


def fit_family_policy(prepared, conservative, search_region, *, noise_sha256=None):
    """Bind owned in-memory history and evaluate the original paired family policy."""
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], family_fit=None, recovery_complete=False)
    history, phase_forecast, history_sha256 = _bound_history(prepared)
    scan = _context(prepared, search_region, noise_sha256, genuine=True)
    result = history_policy(scan, conservative, history, phase_forecast,
        case='SCAN', cutoff_utc_ns=prepared['sky']['metadata']['cutoff_utc_ns'],
        history_sha256=history_sha256)
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


def recover_predictive_tracks(prepared_recovery, *, run_stage, discovery_allowed):
    """Run ordered recovery with explicit caller-owned admission and execution."""
    if prepared_recovery['status'] != 'track_recovery_prepared':
        return dict(status=prepared_recovery['status'], recovery=None, recovery_complete=False)
    result = recover_tracks(prepared_recovery['recovery_context'], prepared_recovery['inventory'],
                            run_stage=run_stage, discovery_allowed=discovery_allowed)
    return dict(status='predictive_recovery_evaluated', recovery=result, recovery_complete=False)


def recover_predictive_checkpoint(prepared_recovery, *, run_stage, discovery_allowed, clock,
                                  inventory_seconds):
    """Keep owned stage values for the immediately following numerical policy."""
    completed = {'inventory': dict(value=prepared_recovery['inventory'], seconds=inventory_seconds)}

    def captured(name, operation):
        began = clock()
        ok, value = run_stage(name, operation)
        if ok:
            completed[name] = dict(value=value, seconds=clock() - began)
        return ok, value

    result = recover_predictive_tracks(prepared_recovery, run_stage=captured,
                                      discovery_allowed=discovery_allowed)
    return dict(result, completed_stages=completed)


def recover_numerical_tracks(prepared_recovery, predictive, *, run_stage,
                             discovery_allowed, clock, charge_reused):
    """Replay the owned checkpoint and retain the exact incumbent on rejection."""
    if predictive['status'] != 'predictive_recovery_evaluated':
        return dict(status=predictive['status'], recovery=None, recovery_complete=False)
    result = replay_recovery(prepared_recovery['recovery_context'], prepared_recovery['inventory'],
        predictive['recovery'], predictive['completed_stages'], run_stage=run_stage,
        discovery_allowed=discovery_allowed, clock=clock, charge_reused=charge_reused)
    return dict(status='numerical_recovery_evaluated', recovery=result, recovery_complete=False)


def recover_numerical_checkpoint(prepared_recovery, predictive, *, run_stage,
                                 discovery_allowed, clock, charge_reused):
    """Retain completed numerical annotations, including on incumbent fallback."""
    completed = {}

    def captured(name, operation):
        ok, value = run_stage(name, operation)
        if ok:
            completed[name] = value
        return ok, value

    result = recover_numerical_tracks(prepared_recovery, predictive, run_stage=captured,
        discovery_allowed=discovery_allowed, clock=clock, charge_reused=charge_reused)
    return dict(result, completed_stages=completed)


def recover_gap_tracks(prepared_recovery, numerical, observations, *, run_stage, clock,
                       maximum_seconds=1200):
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
        maximum_seconds=maximum_seconds)
    return dict(status='gap_recovery_evaluated', recovery=result, incumbent=previous,
                recovery_complete=False)


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
    context = reconstruct_incumbent(prepared_recovery['recovery_context'], arms, owners,
        selection=selection, inventory=prepared_recovery['inventory']['inventory'],
        annotations=annotations, observations=native['observations'])
    ranked = rank_targets(native['tracks'], native['observations'], owners, identities)
    packet = preflight(context, ranked['targets'], scan_receipt)
    return dict(status='additional_recovery_prepared', residual_context=context,
                residual_inventory=ranked, preflight=packet, recovery_complete=False)
