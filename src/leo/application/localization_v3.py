"""Standalone preparation and initial regional position search.

No earlier ALGO jobs or result stores are inputs. Conservative refitting is
included; later family/history fitting and ordered recovery remain unfinished.
"""
from leo.analysis.localization_v3.conservative_recovery import conservative_recovery
from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.initial_search import initial_search
from leo.analysis.localization_v3.noise import estimate_noise
from leo.analysis.localization_v3.phase_prior import forecast
from leo.analysis.localization_v3.scan import ScanLikelihood
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
    sky = prepared['sky']
    scan = ScanLikelihood(prepared['tracks']['tracks'], sky['bank'], sky['nominal_elements'],
        origin_utc_ns=sky['metadata']['origin_utc_ns'],
        regional_center=sky['metadata']['regional_center'], noise=prepared['noise'],
        noise_sha256=noise_sha256, search_region=search_region,
        previous_tle=sky['previous_tle'],
        previous_tle_sha256=sky['previous_receipt']['catalogue_sha256'],
        previous_sources=sky['previous_receipt'].get('sources'))
    result = initial_search(scan, scan.radio_sigma_hz, on_branch=on_branch)
    return dict(status='initial_position_fitted', initial_fit=result, recovery_complete=False)


def refit_initial_position(prepared, initial, search_region, *, noise_sha256=None, on_round=None):
    """Use a fresh context for the genuine-previous prior and conservative recovery.

    Later family-weighted and predictive recovery policies are not yet complete.
    """
    if prepared['status'] != 'inputs_prepared':
        return dict(status=prepared['status'], conservative_fit=None, recovery_complete=False)
    sky = prepared['sky']
    scan = ScanLikelihood(prepared['tracks']['tracks'], sky['bank'], sky['nominal_elements'],
        origin_utc_ns=sky['metadata']['origin_utc_ns'],
        regional_center=sky['metadata']['regional_center'], noise=prepared['noise'],
        noise_sha256=noise_sha256, search_region=search_region,
        previous_tle=sky['genuine_previous_tle'],
        previous_tle_sha256=sky['genuine_previous_receipt']['catalogue_sha256'],
        previous_sources=sky['genuine_previous_receipt']['sources'])
    result = conservative_recovery(scan, initial, prepared['tracks']['observations'],
                                    on_round=on_round)
    return dict(status='conservative_fit_evaluated', conservative_fit=result,
                recovery_complete=False)
