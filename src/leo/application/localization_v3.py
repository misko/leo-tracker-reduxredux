"""Standalone preparation and initial regional position search.

No earlier ALGO jobs or result stores are inputs. Initial, conservative and
family/history and signed-prior fitting are included; later ordered recovery
remains unfinished.
"""
import hashlib
import json

from leo.analysis.localization_v3.conservative_recovery import conservative_recovery
from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.history_policy import history_policy
from leo.analysis.localization_v3.initial_search import initial_search
from leo.analysis.localization_v3.noise import estimate_noise
from leo.analysis.localization_v3.phase_prior import forecast
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.localization_v3.signed_context import signed_context
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.operations.localization_v3_inputs import prepare_initial_sky, prepare_phase_history


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
