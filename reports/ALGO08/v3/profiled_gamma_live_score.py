"""Check the scientific gate before authorizing a profiled full-short dense replay."""

import argparse
from pathlib import Path
from math import isfinite

from aperture_trial import ARMS, read, write
from cold_track_row_trial import REPLAY_PIN
from cold_track_row_transfer import DENSE
from dense_geographic_trial import difference, host
from profiled_gamma_live import PINNED, digest
from profiled_gamma_live_trial import HERE, SMALL


ENDPOINT_KM = .0005
RF_HZ = .01
SCORE = 1e-4
PHYSICAL = HERE.parents[1] / "2026_11_21_ds30_full/reference-audit.json"
PUBLIC = HERE.parent / "regional-release/scoring-key.json"
PHYSICAL_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
PUBLIC_PIN = "0bda865a20e62852220a9ab8df63895a449bf203a2deb5370920dc3ce215d37d"


def coordinates(doc):
    half, width, size = doc["box_width_km"] / 2, doc["box_width_km"], doc["coarse_size"]
    axis = {-half + width * i / (size - 1) for i in range(size)}
    return [(p["east_km"], p["north_km"]) for p in doc["points"] if p["east_km"] in axis and p["north_km"] in axis]


def grid_comparison(control, profiled):
    base, candidate = control["grid"], profiled["grid"]
    if base is None or candidate is None:
        return dict(complete=False)
    rows = (base["points"], candidate["points"])
    grids = [{(p["east_km"], p["north_km"]): p["scores"] for p in row} for row in rows]
    fixed = [coordinates(doc) for doc in (base, candidate)]
    finite = all(v is not None and isfinite(v) for row in rows for p in row for v in p["scores"].values())
    drift, minima = {}, {}
    if finite:
        for arm in ARMS:
            drift[arm] = max((abs(grids[0][x][arm]-grids[1][x][arm]) for x in set(fixed[0]) & set(fixed[1])), default=None)
            minima[arm] = [min(range(len(row)), key=lambda i: row[i]["scores"][arm]) for row in rows]
    return dict(complete=bool(base["complete"] and candidate["complete"] and len(rows[0]) == len(rows[1])),
                same_coarse=bool(fixed[0] == fixed[1] and len(fixed[0]) == base["coarse_size"]**2),
                finite=finite, max_coarse_score_drift=drift, minima=minima,
                score_gate=bool(drift and all(v is not None and v <= SCORE for v in drift.values())),
                minimum_gate=bool(minima and all(pair[0] == pair[1] for pair in minima.values())))


def route_state(attempt):
    if attempt is None:
        return None
    cold = attempt.get("cold", {})
    warm = attempt.get("warm_signed_fit", {})
    return dict(decision=attempt["decision"], reason=attempt.get("reason"), cold=cold.get("routing"),
                winner=cold.get("branch"), complete_finalists=len(cold.get("completed", [])),
                signed=attempt.get("signed", {}).get("status"), warm=warm.get("accepted"),
                warm_reasons=warm.get("reasons"))


def published(folder, mode):
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    process = read(folder / f"{mode}-process.json")
    if process["status"] != 0:
        return dict(process=process, terminal=None)
    root = folder / mode
    report, recipe = (read(root / name) for name in ("joint-research-receipt.json", "full-short-recipe.json"))
    receipt = report["receipt"]
    identifier = receipt["run_id"]
    terminal = read(root / "fast-scan-automatic-work" / identifier / "terminal.json")
    native, = (root / "fast-scan-automatic-work").glob("*/detections.json")
    if (terminal["native_sha256"] != process["native_sha256"] or canonical_digest(terminal) != receipt["terminal_sha256"]
            or canonical_digest(read(native)) != terminal["native_sha256"] or report["saved_digest"] != terminal["native_sha256"]
            or receipt["region"] != process["offer"] or terminal["region"] != process["offer"]
            or report["input"] != "saved detector" or recipe["graph"] != "installed"
            or not recipe["geographic_sha256"] or recipe.get("reuse_cold_track_rows")
            or bool(recipe.get("profiled_gamma")) != (mode == "profiled")):
        raise ValueError("Published saved scientific evidence or proof provenance did not bind to the assigned case")
    store = FastStandardAnalysisStore(root)
    detail = store.detail(identifier)
    proof, = report["early_regional"]
    published_images = artifacts(root, receipt)["images"]
    if canonical_digest(published_images) != canonical_digest(report["evidence"]["images"]):
        raise ValueError("The official publication image hashes changed")
    complete = receipt["decision"] == "complete"
    grid = store.position_grid(identifier) if complete else None
    path = store.position_path(identifier) if complete else None
    detail_arms = detail["arms"]
    history_shape = [{arm: [len(r["points"]) for r in stage["arms"][arm]["rounds"]] for arm in ARMS}
                     for stage in path["stages"]] if path else None
    return dict(process=process, terminal=terminal, decision=receipt["decision"], solve=report["solve"], route=report["route"],
                proof=proof, arms=terminal["arms"], owners={arm: value["owner_sha256"] for arm, value in detail_arms.items()
                                                          if "owner_sha256" in value}, selected=report["selected_rows"],
                grid=grid, path_shape=history_shape, handoff=receipt.get("posterior_grid_handoff", {}),
                grid_kernel=report["solve"]["reduced_grid"],
                route_state=route_state(report["route_details"]), gamma=report.get("profiled_gamma"),
                stage_clocks={key: value for key, value in (report["route_details"] or {}).items() if key.endswith("_clocks")},
                images=report["evidence"]["images"], publication={k: report[k] for k in ("publication_cpu_s", "publication_elapsed_s")},
                report_sha256=digest(root / "joint-research-receipt.json"))


def dense_control():
    if digest(DENSE) != REPLAY_PIN:
        raise ValueError("The original 25.565-second dense archived control changed")
    record = read(DENSE)
    replay = record["objective_replay"]
    if replay != record["grid"]["endpoint_objective_replay"]:
        raise ValueError("Historical dense endpoint replay has inconsistent numerical evidence")
    attempt, = record["attempts"]
    return dict(terminal=dict(native_sha256=record["raw"]["raw_native_sha256"], reason=record["reason"],
                              orbit_policy=record["orbit_policy"], region=record["raw"]["holder"]["offer"]),
                decision="complete" if record["status"] == "ok" else record["status"], proof=record["regional"][0],
                solve=dict(record["solve"], objective_replay=replay), arms=record["arms"], owners=record["owners"],
                selected=record["selected_rows"], stage_clocks={k: v for k, v in attempt.items() if k.endswith("_clocks")},
                grid=record["grid"], handoff=record["posterior_grid_handoff"], grid_kernel=record["grid_kernel"],
                route=attempt["decision"], route_state=route_state(attempt), images={}, path_shape=None, publication=None,
                report_sha256=REPLAY_PIN)


def knowledge(case):
    path, expected = (PUBLIC, PUBLIC_PIN) if case.startswith("south") else (PHYSICAL, PHYSICAL_PIN)
    if digest(path) != expected:
        raise ValueError("The previously published survey reference changed")
    cases = read(path)
    if case.startswith("south"):
        return next(row["truth"] for row in cases["answers"].values() if row["recording"] == "6bd1f26bfa0bedfcf3f100f8")
    label = "DS30-0008" if case == "dense" else "DS30-0016"
    row, = [row["reference"] for row in cases["cases"] if row["dataset_label"] == label and row["authority_eligible"]]
    return [row[k] for k in ("latitude_deg", "longitude_deg")]


def measured_arms(row, truth):
    from tools.pipeline_eval.scoring import distance_km

    values = row.get("arms", {})
    return {arm: dict(latlon=values.get(arm, {}).get("latlon"), rf_rms_hz=values.get(arm, {}).get("rf_rms_hz"),
                      horizontal_error_km=None if values.get(arm, {}).get("latlon") is None
                      else distance_km(values[arm]["latlon"], truth), owners=len(row.get("selected", {}).get(arm, [])))
            for arm in ARMS}


def posterior_coverage(control, profiled):
    old, new = (row["handoff"] for row in (control, profiled))
    old_kernel, new_kernel = (row["grid_kernel"] for row in (control, profiled))
    if (old.get("arithmetic") != new.get("arithmetic")
            or any(old.get(k, 0) != new.get(k, 0) for k in ("factor_calls", "prediction_calls", "dense_calls"))
            or old_kernel.get("grid_calls") != new_kernel.get("grid_calls") or new_kernel.get("grid_calls") != 1
            or any(old_kernel.get(k, 0) != new_kernel.get(k, 0) for k in ("reduced_calls", "original_fallback_calls"))):
        return False
    prediction = new.get("prediction_calls", 0)
    if prediction:
        return prediction == new.get("factor_calls", 0) + new.get("dense_calls", 0)
    return (not new.get("factor_calls") and not new.get("dense_calls") and not new_kernel.get("reduced_calls")
            and profiled["gamma"]["activity"].get("ordinary_grid_bypasses", 0) > 0)


def science_gate(control, profiled, *, far, dense):
    from leo.contracts.fast_standard_analysis import PLOTS
    from tools.pipeline_eval.scoring import distance_km

    if any(row["terminal"] is None for row in (control, profiled)):
        return dict(both_publications_finished=False), {}, {}
    terminals = [row["terminal"] for row in (control, profiled)]
    gamma = profiled["gamma"]
    counts, activity = gamma["counts"], gamma["activity"]
    checks = dict(native_offer=all(terminals[0][key] == terminals[1][key] for key in ("native_sha256", "region", "reason", "orbit_policy")),
                  regional=control["proof"]["result"] == profiled["proof"]["result"],
                  state=control["route"] == profiled["route"] and control["route_state"] == profiled["route_state"],
                  decisions=control["decision"] == profiled["decision"] == ("withheld" if far else "complete"),
                  gamma_binding=gamma["provenance"]["binary_sha256"] == PINNED["binary_sha256"] and
                  (activity.get("profiled_calls", 0) > 0) == (not far))
    if far:
        from proof_rank_short_transfer import saved_far

        proof = profiled["proof"]["result"]
        archived = saved_far()["proof"]["result"]
        checks["bilateral_early_without_native_fit"] = (
            profiled["route"] == "withheld_early" and profiled["route_state"] is None and not profiled["images"]
            and receipt_withholds(terminals[1]) and proof["probes_evaluated"] == 96 and proof["would_withhold"]
            and proof["complete"] and set(proof["receivers"]) == {"1", "2"}
            and all(row["unique_exterior"] for row in proof["receivers"].values())
            and not profiled["handoff"].get("prediction_calls") and not counts.get("evaluations")
            and difference(proof, archived) <= 1e-8)
        return checks, {}, {}
    changes = {arm: dict(shift_km=distance_km(control["arms"][arm]["latlon"], profiled["arms"][arm]["latlon"]),
                         rf_delta_hz=profiled["arms"][arm]["rf_rms_hz"]-control["arms"][arm]["rf_rms_hz"])
               for arm in ARMS if all(row["arms"].get(arm, {}).get("latlon") is not None for row in (control, profiled))}
    observed = grid_comparison(control, profiled)
    images = {name: dict(same_size=image["size"] == control["images"][name]["size"],
                         same_sha256=image["sha256"] == control["images"][name]["sha256"],
                         same_pixels=image["rgba_sha256"] == control["images"][name]["rgba_sha256"])
              for name, image in profiled["images"].items() if name in control["images"]}
    checks.update(movement=len(changes) == 2 and all(row["shift_km"] <= ENDPOINT_KM and abs(row["rf_delta_hz"]) <= RF_HZ
                                                    for row in changes.values()),
                  owners_and_roles=control["selected"] == profiled["selected"] and control["owners"] == profiled["owners"],
                  evidence=all(observed.get(k) for k in ("complete", "same_coarse", "finite", "score_gate", "minimum_gate")),
                  official_images=set(profiled["images"]) == set(PLOTS) and
                  (dense or set(images) == set(PLOTS) and all(row["same_size"] for row in images.values())),
                  handoff=posterior_coverage(control, profiled),
                  replay=profiled["solve"].get("objective_replay") == control["solve"].get("objective_replay") == dict.fromkeys(ARMS, 0.))
    return checks, changes, dict(grid=observed, images=images,
                                 path_round_sizes=None if dense else profiled["path_shape"] == control["path_shape"])


def receipt_withholds(doc):
    return (doc["reason"] == "both_receivers_support_far_exterior"
            and all(doc["arms"][arm]["latlon"] is None for arm in ARMS))


def score(case, root, output):
    host()
    folder = root / case
    binding = read(folder / "binding.json")
    if binding["case"] != case or binding["protocol_sha256"] != digest(HERE / "profiled-gamma-live-protocol.md"):
        raise ValueError("Unexpected comparison input or changed frozen protocol")
    base = dense_control() if case == "dense" else published(folder, "control")
    trial = published(folder, "profiled")
    checks, changes, evidence = science_gate(base, trial, far=case == "south-far", dense=case == "dense")
    truth = knowledge(case)
    arms = {key: measured_arms(row, truth) for key, row in (("control", base), ("profiled", trial))}
    for arm in changes:
        changes[arm]["horizontal_error_delta_km"] = arms["profiled"][arm]["horizontal_error_km"] - arms["control"][arm]["horizontal_error_km"]
    write(output, dict(case=case, passed=all(checks.values()), checks=checks, changes=changes, evidence=evidence,
                       arms=arms, control=base, profiled=trial, binding=binding, source_sha256=digest(Path(__file__))))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=(*SMALL, "dense"))
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    score(**vars(cli.parse_args()))
