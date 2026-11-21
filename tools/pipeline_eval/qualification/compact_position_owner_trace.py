"""Record the compact solver's actual publication support during an unchanged replay."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.variants import v5_core, v5_secant_fit


def arm_trace(arm, entries):
    groups = []
    predictive = {(e["component"], tuple(e["observation_ids"])): int(e["norad"]) for e in entries}
    for kind, gates in (
        ("curved", arm["gates"]["tracks"]),
        ("predictive", arm.get("linear_gates", [])),
    ):
        for gate in gates:
            norad = gate.get("norad")
            if kind == "predictive":
                selected = predictive[(gate["component"], tuple(gate["observation_ids"]))]
                if norad is not None and int(norad) != selected:
                    raise ValueError("predictive gate and selected model disagree about ownership")
                norad = selected
            groups.append(
                dict(
                    kind=kind,
                    component=gate["component"],
                    norad=int(norad),
                    compatible=bool(gate["compatible"]),
                    ids=list(gate["observation_ids"]),
                )
            )
    return dict(latlon=list(arm["endpoint_latlon"]), rf_rms_hz=float(arm["RMS_hz"]), groups=groups)


def previous_orbit_failure(request, result, library):
    import numpy as np
    from leo.analysis.localization_v3 import orbit_modes
    from sgp4.api import SGP4_ERRORS

    from leo.sky.propagation import julian_day_from_utc_ns

    original = orbit_modes.ecef_states

    def record(catalogue, origin, times):
        values = original(catalogue, origin, times)
        if not values[2].all():
            jd, fr = julian_day_from_utc_ns(
                origin + np.rint(np.array(times) * 1e9).astype(np.int64)
            )
            failed = {}
            for n, sat, good in zip(
                catalogue.satellite_numbers, catalogue.satellites, values[2], strict=True
            ):
                if not good:
                    errors, _, _ = sat.sgp4_array(jd, fr)
                    failed[str(n)] = {
                        str(int(i)): str(SGP4_ERRORS[int(i)]) for i in np.unique(errors) if i
                    }
            save_json(
                Path(result).with_name("previous-orbit-failure.json"),
                dict(
                    numerical_time_s=list(map(float, times)),
                    origin_utc_ns=int(origin),
                    selected=list(map(int, catalogue.satellite_numbers)),
                    failed=failed,
                ),
            )
        return values

    with patch.object(orbit_modes, "ecef_states", record):
        v5_secant_fit.worker(request, result, library, "secant")


def worker(request, result, library, mode="trace"):
    if mode == "previous_orbit_failure":
        return previous_orbit_failure(request, result, library)
    from leo.analysis.localization_v3 import family_cavity

    trace = {}
    original_infer = v5_core.infer
    original_nominate = family_cavity.nominate_families
    original_policy = family_cavity.cavity_policy

    def infer(prepared, *args, **kwargs):
        tracks = prepared["tracks"]
        trace["graph"] = [
            dict(
                component=t["key"],
                ids=list(t["observation_ids"]),
                curved=i in tracks["curved_indices"],
            )
            for i, t in enumerate(tracks["tracks"])
        ]
        trace["cutoff_utc_ns"] = int(prepared["sky"]["metadata"]["cutoff_utc_ns"])
        return original_infer(prepared, *args, **kwargs)

    def nominate(context):
        trace["arms"] = {a: arm_trace(r, context["entries"]) for a, r in context["arms"].items()}
        trace["cavity_selected"] = False
        return original_nominate(context)

    def policy(context, nominations):
        fit = original_policy(context, nominations)
        if fit["status"] == "complete":
            chosen = fit["selected"] if fit["accepted"] else None
            entries = chosen["entries"] if chosen is not None else fit["baseline_entries"]
            trace["arms"] = {a: arm_trace(r, entries) for a, r in fit["policy_arms"].items()}
            trace["cavity_selected"] = bool(fit["accepted"])
        return fit

    with (
        patch.object(v5_core, "infer", infer),
        patch.object(family_cavity, "nominate_families", nominate),
        patch.object(family_cavity, "cavity_policy", policy),
    ):
        v5_secant_fit.worker(request, result, library, "secant")
    document = json.loads(Path(result).read_bytes())
    for name, arm in document["arms"].items():
        saved = trace["arms"][name]
        if arm["latlon"] != saved["latlon"] or arm["rf_rms_hz"] != saved["rf_rms_hz"]:
            raise ValueError("captured support belongs to a different endpoint")
    save_json(Path(result).with_name("owner-trace.json"), trace)


if __name__ == "__main__":
    worker(*sys.argv[1:])
