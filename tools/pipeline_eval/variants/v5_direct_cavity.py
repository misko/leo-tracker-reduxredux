"""Direct stored-native compact v5 inference through the paired cavity decision."""

import argparse
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from time import perf_counter

from tools.pipeline_eval.variants import orbit_projector, v5_core
from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant

METHOD = "v5_direct_cavity"
BOUNDARY = "Stored native GLRT and causal TLEs through the compact v5 cavity decision"
ARMS = ("c0", "fitted_c")
_numerical_lock = Lock()


def verified_json(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError("input content differs from its declared SHA-256")
    return json.loads(raw)


@contextmanager
def numerical_bindings(projector):
    """Bind the two numerical ports absent from the frozen science API."""
    from leo.analysis.localization_v3 import (
        conservative_recovery,
        discovery,
        family_weighting,
        position,
        scan,
    )

    from leo.analysis.research.phase_linear_geometry import phase_linear_frequency

    def evaluate(grid, *args, **kwargs):
        operation = (
            projector.evaluate
            if isinstance(grid, orbit_projector.Stencil)
            else phase_linear_frequency
        )
        return operation(grid, *args, **kwargs)

    routes = (
        (scan, "prepare_phase_geometry", orbit_projector.prepare),
        (position, "bounded_gauss_newton", bounded_secant),
        *(
            (m, "phase_linear_frequency", evaluate)
            for m in (scan, discovery, family_weighting, conservative_recovery)
        ),
    )
    with _numerical_lock:
        previous = [(m, key, getattr(m, key)) for m, key, _ in routes]
        try:
            for place, key, value in routes:
                setattr(place, key, value)
            yield
        finally:
            for place, key, value in previous:
                setattr(place, key, value)


def nominal_families(context, nominate):
    """Release the nominal problem once leave-family-out scoring is finished."""
    try:
        return nominate(context)
    finally:
        problem = context.pop("base")
        for key in (
            "calculate",
            "curved_calculate",
            "state",
            "conditional_frequency",
            "_fixed_phase_geometry_cache",
        ):
            problem.__dict__.pop(key, None)


def digest(value):
    return hashlib.sha256((json.dumps(value, sort_keys=True) + "\n").encode()).hexdigest()


def infer(prepared, region, bound, stages):
    from leo.analysis.localization_v3.conservative_recovery import conservative_recovery
    from leo.analysis.localization_v3.family_cavity import cavity_policy, nominate_families
    from leo.analysis.localization_v3.history_policy import history_policy
    from leo.analysis.localization_v3.signed_context import signed_context

    def withheld(reason):
        return dict(
            status="withheld",
            boundary=BOUNDARY,
            reason=reason,
            arms={a: {"latlon": None} for a in ARMS},
            metrics=dict(stage_s=stages),
        )

    if prepared["status"] != "inputs_prepared":
        return withheld(prepared["status"])
    observations = prepared["tracks"]["observations"]
    started = perf_counter()
    noise = digest(prepared["noise"])
    first = v5_core.scan_context(prepared, region, noise, bound, "previous")
    initial, branches = v5_core.initial_selection(first)
    del first
    stages["initial"] = perf_counter() - started

    started = perf_counter()
    scan = v5_core.scan_context(prepared, region, noise, bound, "genuine_previous")
    conservative = conservative_recovery(scan, initial, observations)
    stages["conservative"] = perf_counter() - started
    if conservative["status"] != "complete":
        return withheld(conservative["status"])
    history = prepared["phase_history"]
    history_sha = digest(history)
    forecast = dict(prepared["phase_forecast"], history_sha256=history_sha)
    if prepared["phase_forecast"].get("history_sha256", history_sha) != history_sha:
        raise ValueError("causal phase history has changed")
    policy = dict(
        case="SCAN",
        cutoff_utc_ns=prepared["sky"]["metadata"]["cutoff_utc_ns"],
        history_sha256=history_sha,
    )
    started = perf_counter()
    family = history_policy(scan, conservative, history, forecast, **policy)
    stages["family"] = perf_counter() - started
    if family["status"] != "accepted":
        return withheld(family["status"])
    started = perf_counter()
    signed = signed_context(scan, conservative, family, history, forecast, observations, **policy)
    stages["signed"] = perf_counter() - started
    del conservative, family

    started = perf_counter()
    nominations = nominal_families(signed, nominate_families)
    if nominations["status"] != "complete":
        raise ValueError(f"cavity nomination failed: {nominations.get('error')}")
    offered = any(
        x["best"] is not None and x["predictive_gain"] > 0 for x in nominations["families"]
    )
    arms = signed["arms"]
    if offered:
        cavity = cavity_policy(signed, nominations)
        if cavity["status"] != "complete":
            raise ValueError(f"cavity fit failed: {cavity.get('error')}")
        arms = cavity["policy_arms"]
    stages["cavity"] = perf_counter() - started
    return dict(
        status="ok",
        boundary=BOUNDARY,
        arms={
            a: dict(latlon=list(arms[a]["endpoint_latlon"]), rf_rms_hz=float(arms[a]["RMS_hz"]))
            for a in ARMS
        },
        metrics=dict(
            stage_s=stages,
            initial_branches=branches,
            initial_arm_fits=branches,
            cavity_offered=offered,
            observations=len(observations),
            tracks=len(prepared["tracks"]["tracks"]),
            **{
                f"{a}_frequency_score": float(arms[a]["negative_twice_elbo"])
                for a in ARMS
                if arms[a].get("negative_twice_elbo") is not None
            },
        ),
    )


def solve(document, *, archive, track_config, screen_center, region, library, bound):
    """Use explicit inputs from a dedicated process owning the numerical bindings."""
    from leo.application.localization_v3 import prepare_native_scan
    from leo.application.localization_v3_engine import _prepared_values

    start = perf_counter()
    prepared = _prepared_values(
        prepare_native_scan(
            document,
            archive,
            track_config,
            screen_latitude_deg=screen_center[0],
            screen_longitude_deg=screen_center[1],
        )
    )
    projector = orbit_projector.Projector(library)
    with numerical_bindings(projector):
        result = infer(prepared, region, bound, {"native_preparation": perf_counter() - start})
    result["metrics"]["compact_projections"] = projector.calls
    return result


def run(
    native,
    *,
    native_sha256,
    track_config,
    config_sha256,
    session,
    archive,
    native_backend,
    library,
    tile,
    screen_center,
    width_km=25.0,
):
    """Read one native factor file and its explicitly supplied receiver configuration."""
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
    from leo.analysis.localization_v4.native_bound import NativeBound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    document = verified_json(native, native_sha256)
    if document["source"]["session_id"] != session:
        raise ValueError("native observations belong to a different session")
    config = verified_json(track_config, config_sha256)["config"]
    manifest = validate_manifest(read_manifest(native_backend), check_provider=True)
    return solve(
        document,
        archive=TleArchiveReader(Path(archive)),
        track_config=TrackConfig(**config),
        region=SearchRegion(tuple(tile), width_km=width_km),
        screen_center=screen_center,
        library=library,
        bound=NativeBound(manifest["binary"]),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in (
        "native",
        "native-sha256",
        "track-config",
        "config-sha256",
        "session",
        "archive",
        "native-backend",
        "library",
    ):
        parser.add_argument(f"--{flag}", required=True)
    parser.add_argument("--tile", type=float, nargs=2, required=True)
    parser.add_argument("--screen-center", type=float, nargs=2, required=True)
    parser.add_argument("--width-km", type=float, default=25)
    args = vars(parser.parse_args())
    print(json.dumps(run(**args), allow_nan=False))


if __name__ == "__main__":
    main()
