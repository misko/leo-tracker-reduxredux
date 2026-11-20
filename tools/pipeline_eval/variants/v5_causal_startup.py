"""Prepare a provisional causal orbit bank before native observations become available."""

from dataclasses import dataclass
from time import perf_counter

from . import orbit_projector
from . import v5_direct_cavity as direct

METHOD = "v5_causal_startup"
BOUNDARY = "Early causal sky and phase history through the same compact cavity decision"
NOMINAL_S = 300.0


def metadata(anchor):
    before, after = (anchor[k]["realtime_ns"] for k in ("before", "after"))
    if not 0 <= after - before <= 2_000_000_000:
        raise ValueError("invalid first-delivery UTC bracket")
    return {"anchor_utc_ns": (before + after) // 2, "causal_cutoff_utc_ns": before}


@dataclass
class Startup:
    authority: dict
    screen: tuple
    archive: object
    sky: dict
    history: dict
    forecast: dict
    stages: dict


def prepare(archive, anchor, screen):
    """Use only the opening clock bracket, configured screen and nominal schedule."""
    from leo.analysis.localization_v3.elements import ElementParser

    from leo.application import localization_v3 as app

    authority = metadata(anchor)
    lat, lon = screen
    parser = ElementParser()
    t = perf_counter()
    # The frozen sky builder uses its track argument solely to get the horizon.
    # This view supplies schedule time, with no GLRT sample or fitted track.
    sky = app.prepare_initial_sky(
        archive,
        ({"times": (NOMINAL_S,)},),
        authority,
        element_parser=parser,
        screen_latitude_deg=lat,
        screen_longitude_deg=lon,
    )
    stages = {"sky": perf_counter() - t}
    t = perf_counter()
    history = app.prepare_phase_history(
        archive, sky["nominal_elements"], authority, element_parser=parser
    )
    stages["history"] = perf_counter() - t
    t = perf_counter()
    forecast = app.forecast(history)
    stages["forecast"] = perf_counter() - t
    return Startup(authority, tuple(screen), archive, sky, history, forecast, stages)


def reuse_authorized(startup, tracks, screen, archive):
    duration = max(NOMINAL_S, max(float(row["times"][-1]) for row in tracks["tracks"]))
    same = (
        duration == NOMINAL_S
        and archive is startup.archive
        and tuple(screen) == startup.screen
        and all(tracks["metadata"][k] == v for k, v in startup.authority.items())
    )
    return same, duration


def finish(document, startup, *, archive, track_config, screen_center, region, library, bound):
    """Validate the final observation horizon, then use the original cavity inference."""
    from leo.application.localization_v3_engine import _prepared_values

    from leo.application import localization_v3 as app

    started = perf_counter()
    tracks = app.prepare_tracks(document, track_config)
    prepared = {"status": tracks["status"], "tracks": tracks, "sky": None}
    used, duration = False, None
    if tracks["status"] == "tracks_prepared":
        used, duration = reuse_authorized(startup, tracks, screen_center, archive)
        if used:
            prepared.update(
                status="inputs_prepared",
                sky=startup.sky,
                phase_history=startup.history,
                phase_forecast=startup.forecast,
                noise=app.estimate_noise(tracks["tracks"], tracks["observations"]),
            )
    if tracks["status"] == "tracks_prepared" and not used:
        # Drop a mismatched speculative bank before normal preparation.
        startup.sky.clear()
        startup.history.clear()
        startup.forecast.clear()
        prepared = app.prepare_native_scan(
            document,
            archive,
            track_config,
            screen_latitude_deg=screen_center[0],
            screen_longitude_deg=screen_center[1],
        )
    projector = orbit_projector.Projector(library)
    with direct.numerical_bindings(projector):
        result = direct.infer(
            _prepared_values(prepared),
            region,
            bound,
            {"native_preparation": perf_counter() - started},
        )
    result["metrics"].update(
        compact_projections=projector.calls, early_orbit_reused=used, final_track_horizon_s=duration
    )
    result["boundary"] = BOUNDARY
    return result
