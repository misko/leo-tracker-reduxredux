"""Read the frozen DS30-0163 full-member comparisons only after sealing the replay."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alternate_original_members_0163 import (CONTROL, CONTROL_PIN, CONTROL_SEAL, DESCRIPTION, TRANSFER,
                                             digest, frozen_sources, read)
from alternate_original_members import LIMIT_KM
from alternate_original_members_score import ARMS, geographic, grid_summary


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from clean_saved_publication import load_job
    from ds30_0163_composed_saved import controls
    from empty_bootstrap import checked
    from history_risk_cairo_physical import clean
    from unseen_saved_holdout_score import REFERENCE_PIN
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect, owner_delta

    seal = root / "prediction-seal.json"
    admission, timing = read(root / "admission.json"), read(root / "routed/clock.json")
    if read(seal) != output_seal(root) or admission["member_trial_sources"] != frozen_sources():
        raise ValueError("Require the frozen trial source and sealed candidate products")
    ordinary = json.loads(checked(CONTROL / "result.json", CONTROL_PIN))
    if (not ordinary["qualified"] or ordinary["admission"]["job_sha256"] != TRANSFER.job_pin
            or ordinary["prediction_sha256"] != CONTROL_SEAL
            or json.loads(checked(CONTROL / "prediction-seal.json", CONTROL_SEAL)) != output_seal(CONTROL)):
        raise ValueError("Require the existing qualified full composed control and its products")
    archived = controls(TRANSFER)
    archives = json.loads(checked(TRANSFER.original / "prediction-seal.json", TRANSFER.seal_pin))
    if archives != output_seal(TRANSFER.original):
        raise ValueError("The installed comparison files changed")
    old, stock = ordinary["candidate"], archived["jobs"]["installed"]["publication"]
    import unseen_saved_holdout_score as holdout

    with patch.object(holdout, "CASE", TRANSFER.case):
        truth = holdout.reference()
    estimates = dict(full_composed=geographic(old, truth), installed=geographic(stock, truth))
    clocks = {}
    for metric in ("elapsed_s", "cpu_s"):
        prep = admission["setup"][metric] + admission["smoke"]["clock"][metric]
        clocks[metric] = dict(candidate_child=timing[metric], candidate_setup=prep,
                              candidate_charged=timing[metric] + prep, full_composed_child=ordinary["process"][metric],
                              full_composed_charged=ordinary["cost"][metric]["charged"],
                              installed_child=archived["jobs"]["installed"]["clock"][metric],
                              installed_charged=archived["paid_setup_and_time"][metric]["installed_with_setup"])
    directory = root / "routed/candidate"
    result = dict(case=TRANSFER.case, passed=False, candidate_children=1, process=timing, clocks=clocks,
                  status="failed_child" if timing["exit_code"] else "scored", admission=admission,
                  seal_sha256=digest(seal), estimates=estimates, reference_sha256=REFERENCE_PIN)
    if timing["exit_code"]:
        write(root / "result.json", result)
        return
    try:
        binding, request = load_job(TRANSFER.ready / "job.json", TRANSFER.job_pin)
        receipt = read(directory / "worker.json")["receipt"]
        candidate = inspect(directory, "alternate original compressed members", receipt, timing, request,
                            native_sha=admission["derived_packet_sha256"], windows=binding["issued"],
                            admitted=admission["acquisition"]["retained"]["processed_visits"], audit_name="worker.json",
                            input_description=DESCRIPTION)
        planned = admission["acquisition"]
        counts = receipt["counts"]
        skips = planned["full"]["visits"] - planned["retained"]["visits"]
        if (counts != dict(processed=planned["retained"]["processed_visits"],
                           invalid_capture=planned["retained"]["invalid_capture"], skipped_acquisition=skips,
                           skipped_fast_score=0) or receipt["region"] != old["science"]["receipt"]["region"]):
            raise ValueError("The private research receipt masked unmeasured visits as another status or changed the offer")
        estimates["candidate"] = geographic(candidate, truth)
        comparisons = {mode: {arm: owner_delta(publication["selected_rows"].get(arm, []),
                                               candidate["selected_rows"].get(arm, [])) for arm in ARMS}
                       for mode, publication in (("full_composed", old), ("installed", stock))}
        telemetry = read(root / "composition.json")
        grid_telemetry = read(root / "routed/combined-grid.json")
        route = clean(read(root / "routed/risk-route.json"))
        graph = clean(read(directory / "ports.json")["graph"])
        full_graph = clean(read(CONTROL / "routed/candidate/ports.json")["graph"])
        result.update(candidate=candidate, owner_changes=comparisons, candidate_route=route, full_route=ordinary["route"],
                      candidate_graph=graph, full_graph=full_graph, composition=telemetry, native_grid=grid_telemetry,
                      full_figures=old["figures"], installed_figures=stock["figures"])
        if receipt["decision"] != "complete":
            write(root / "result.json", result | {"status": "withheld"})
            return
        grids = {}
        points = {}
        for label, folder, publication in (("full_composed", CONTROL / "routed/candidate", old),
                                           ("candidate", directory, candidate)):
            store = FastStandardAnalysisStore(folder)
            grids[label], points[label] = grid_summary(store.position_grid(publication["science"]["receipt"]["run_id"]))
        common = points["candidate"].keys() & points["full_composed"].keys()
        if len(common) < 81 or grids["candidate"]["coarse_coordinates"] != grids["full_composed"]["coarse_coordinates"]:
            raise ValueError("The original common coarse grid coordinate set changed")
        deltas = {arm: {name: estimates["candidate"][arm]["horizontal_error_km"] - estimates[name][arm]["horizontal_error_km"]
                        for name in ("full_composed", "installed")} for arm in ARMS}
        passes = all(delta <= LIMIT_KM for by_arm in deltas.values() for delta in by_arm.values())
        agg, png, predictive = (telemetry[key] for key in ("agg", "native_png", "predictive"))
        composition_same = (agg.get("figures"), agg.get("axes"), agg.get("first_restores_elided"), png["native"],
                            png["fallback"], predictive.get("reduced_calls"), predictive.get("original_fallback_calls", 0)) == (
                            2, 16, 2, 8, 0, 356, 0) and not ("ordinary_fallback" in agg or predictive.get("unsupported_binding"))
        pinned_native = grid_telemetry.get("assembly", {}).get("assembly_calls") == 356 and (
            grid_telemetry.get("projection", {}).get("native_selection") == 356)
        composition_same = composition_same and pinned_native
        grid_deltas = {arm: max(abs(points["candidate"][xy][arm] - points["full_composed"][xy][arm]) for xy in common)
                       for arm in ARMS}
        result.update(passed=passes and composition_same, pass_accuracy=passes,
                      status="passed" if passes and composition_same else "failed_screen",
                      composition_activated=composition_same, grid=grids, common_grid_positions=len(common),
                      common_max_abs_score_delta=grid_deltas, position_error_delta_km=deltas)
    except (KeyError, ValueError) as error:
        result.update(status="failed_evidence", evidence_error=str(error))
    write(root / "result.json", result)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    score(parser.parse_args().root)
