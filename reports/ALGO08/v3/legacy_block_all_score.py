"""Verify the all-original indexed child against the already paid ordinary control."""

from collections import Counter

from legacy_block_all_0016 import PREVIOUS, digest, qualified_control, read, runtime_pins
from frame_portable_0016 import seal


def check_members(audit, book):
    plan, preparation = book["plan"], book["preparation"]
    if (audit["custody_sha256"] != book["map_custody_sha256"]
            or audit["binary_sha256"] != preparation["build"]["binary_sha256"]):
        raise ValueError("The selected acquisition did not use the frozen all-member map and decoder pins")
    totals, apertures, spans = Counter(), Counter(), Counter()
    by_member = []
    for ordinal, (actual, expected) in enumerate(zip(audit["members"], plan["members"], strict=True)):
        kind = expected["map_kind"]
        if (any(actual[k] != v for k, v in expected.items()) or actual["authenticated_encoded_bytes"] != expected["encoded"]
                or actual["kind"] != ("ordinary" if kind == "ordinary" else "map")):
            raise ValueError("Actual acquisition changed member identity or the assigned map path")
        totals.update({f"{kind}_members": 1, f"{kind}_windows": expected["windows"],
                       "authenticated_encoded_bytes": expected["encoded"], "committed_bytes": actual["committed_bytes"]})
        if kind == "ordinary":
            if actual["committed_bytes"] != expected["decoded"]:
                raise ValueError("Ordinary fallback did not commit the original complete member scope")
        else:
            if kind == "exception" and "exception_spans" not in actual["spans"]:
                raise ValueError("Expected exact exception and table-owner counters for each matched member")
            apertures.update(actual["counts"])
            spans.update(actual["spans"])
        by_member.append(dict(actual, ordinal=ordinal))
    if totals["authenticated_encoded_bytes"] != 991_734_597 or sum(
            totals[f"{mode}_windows"] for mode in ("literal", "exception", "ordinary")) != 808:
        raise ValueError("The original recording's entire member traversal is required")
    if totals["literal_members"] != 5 or totals["exception_members"]+totals["ordinary_members"] != 8:
        raise ValueError("Unexpected all-member assignment")
    return dict(totals=dict(totals), apertures=dict(apertures), native_spans=dict(spans), members=by_member)


def score(root, control_pin):
    from aperture_trial import write
    from history_risk_residual_layout_0402 import media_identity
    from legacy_block_raw_score import snapshot
    from publication_media_checks import verify_position_sidecars

    control = qualified_control(control_pin)
    ordinary = control["products"]["ordinary"]
    book = read(root / "admission.json")
    checks = dict(source_pins=book["sources"] == runtime_pins(), prediction=read(root / "prediction-seal.json") == seal(root),
                  assigned_request=book["request"] == control["admission"]["request"],
                  original_control=book["preparation"]["ordinary_control_sha256"] == control_pin,
                  same_causal_producer=book["producer"] == control["admission"]["producer"])
    log = read(root / "indexed-clock.json")
    checks["same_command"] = log["command"] == book["commands"]["indexed"]
    if not all(checks.values()):
        raise ValueError("Selected generation recipe or prior ordinary custody changed")
    current = snapshot(root / "indexed", log, book["request"], book["producer"])
    check_receipt = ("decision", "session_id", "run_id", "terminal_sha256", "region", "window_count", "counts")
    checks.update({key: current["receipt"][key] == ordinary["receipt"][key] for key in check_receipt})
    checks.update({key: current[key] == ordinary[key] for key in ("native_sha256", "native_source", "ordered_owners",
                                                                   "positions", "history_risk")})
    checks.update({key: current["published"][key] == ordinary["published"][key]
                   for key in ("raw_authority", "arms", "owners", "scientific_digests")})
    checks["all_figures"] = media_identity(current["images"]) == media_identity(ordinary["images"])
    if not all(checks.values()):
        raise ValueError(f"Scientific products changed: {checks}")
    sidecars = verify_position_sidecars(PREVIOUS / "ordinary", root / "indexed", current["receipt"]["run_id"],
                                        ordinary["images"], current["images"])
    input_audit = check_members(read(root / "indexed/legacy-map-acquisition.json"), book)
    prior = control["products"]["indexed"]["process"]
    prep = book["preparation"]
    amounts = {}
    for metric in ("elapsed_s", "cpu_s"):
        cost = prep["total"][metric] + (prep["build"]["compiler_cpu_s"] if metric == "cpu_s" else 0)
        historic = control["prices"][metric]["measured_full_preparation"]
        amounts[metric] = dict(ordinary=ordinary["process"][metric], five_maps=prior[metric],
            all_members=current["process"][metric], measured_incremental_preparation=cost,
            prior_complete_five_map_validation=historic, first_use_from_verified_five_maps=cost+current["process"][metric],
            all_observed_first_use_with_historical_preparation=cost+historic+current["process"][metric],
            prior_portable_producer=book["prior_index_build"][metric])
    write(root / "result.json", dict(qualified=True, checks=checks, case="DS30-0016", ordinary_control_sha256=control_pin,
        input=input_audit, admission=book, sidecars=sidecars, prices=amounts,
        products=dict(ordinary=ordinary, indexed=current), prediction_seal=digest(root / "prediction-seal.json")))
