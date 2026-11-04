"""Standalone localization orchestration, currently through initial preparation.

No earlier ALGO jobs or result stores are inputs. The subsequent localization
and ordered recovery engine are still under construction.
"""
from leo.analysis.localization_v3.elements import ElementParser
from leo.analysis.localization_v3.noise import estimate_noise
from leo.analysis.localization_v3.phase_prior import forecast
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
