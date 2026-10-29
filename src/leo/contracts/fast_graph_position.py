"""Version one of the causal graph fast-position terminal contract."""

import math

MODEL_VERSION = "algo02-causal-family-v1"
KIND = "fast-scan.graph-position"
ARMS = ("c0", "fitted_c")
CENTER = (37.906, -122.545)


def validate_terminal(document, *, input_sha256):
    if (document.get("schema_version") != 1 or document.get("kind") != KIND
            or document.get("model_version") != MODEL_VERSION
            or document.get("input_sha256") != input_sha256
            or document.get("state") not in {"complete", "unavailable", "failed"}):
        raise ValueError("Graph position terminal identity/state mismatch")
    if document["state"] != "complete":
        if document.get("position") is not None:
            raise ValueError("Unqualified terminal cannot publish a position")
        return document
    if (document.get("reference_usage") != "none" or document.get("future_TLE_used") is not False
            or document.get("selected_arm") != "fitted_c"):
        raise ValueError("Contradictory inference provenance")
    audit = document.get("read_audit", {})
    if (audit.get("receipts", 0) < 4 or audit.get("denied_paths") != []
            or audit.get("all_launched_processes_accounted") is not True
            or audit.get("historical_result_or_GPS_reads") is not False):
        raise ValueError("Complete inference requires successful process read audits")
    if document.get("qualification") != "paired_residual_phase_regional_gates":
        raise ValueError("Complete graph position requires paired qualification")
    if document.get("matched_c_inputs") is not True:
        raise ValueError("Paired observations and hypotheses required")
    for arm in ARMS:
        saved = document["arms"][arm]
        lat, lon = saved["endpoint_latlon"]
        if not all(math.isfinite(v) for v in (lat, lon)) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid geographic endpoint")
        xy = saved["endpoint_east_north_km"]
        if len(xy) != 2 or not all(math.isfinite(v) and abs(v) <= 12.5 + 1e-8 for v in xy):
            raise ValueError("Endpoint outside original regional box")
        expected = (CENTER[0] + xy[1] / 111.0,
                    CENTER[1] + xy[0] / (111.32 * math.cos(math.radians(CENTER[0]))))
        if any(abs(a - b) > 1e-8 for a, b in zip(expected, (lat, lon), strict=True)):
            raise ValueError("Endpoint coordinate systems disagree")
        tracks = saved["gates"]["tracks"] + saved.get("linear_gates", [])
        if not tracks or not all(t["compatible"] is True for t in tracks):
            raise ValueError("A retained track fails residual gates")
        change = saved.get("final_phase_change_s", float("inf"))
        if not math.isfinite(change) or (saved.get("phase_stability_required", True) and change > .01):
            raise ValueError("Orbital phase refresh did not stabilize")
        if not all(math.isfinite(saved[k]) for k in ("RMS_hz", "negative_twice_elbo")):
            raise ValueError("Nonfinite saved frequency objective")
    identities = [[(t["component"], t["points"], t.get("norad"), t.get("observation_ids"))
                   for t in document["arms"][arm]["gates"]["tracks"] + document["arms"][arm].get("linear_gates", [])]
                  for arm in ARMS]
    if identities[0] != identities[1]:
        raise ValueError("Paired c-arm observation identities differ")
    selected = document["arms"]["fitted_c"]["endpoint_latlon"]
    if document["position"] != dict(latitude_deg=selected[0], longitude_deg=selected[1]):
        raise ValueError("Published position differs from fitted-c arm")
    return document
