"""Verify the sealed member-mask solve and open the historical controls."""

import argparse
from hashlib import sha256
from itertools import product
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys

from alternate_original_members import (CASE, CONTROL, CONTROL_SEAL, DESCRIPTION, LIMIT_KM, ROOT, STOCK,
                                        digest, frozen_sources, read)

ARMS = ("c0", "fitted_c")
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
PRE_SEAL_SCORER = "8cff3ff42d6bdde2a7e6a562f14594f2d5168d35874d1b67c3118fb1cb797ab5"


def reference():
    data = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
                                    "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if sha256(data).hexdigest() != REFERENCE_PIN:
        raise ValueError("The independent survey authority changed")
    row, = (item["reference"] for item in json.loads(data)["cases"] if item["dataset_label"] == CASE
            and item["authority_eligible"] and item["sealed_metadata_digests_verified"])
    return [row["latitude_deg"], row["longitude_deg"]]


def grid_summary(grid):
    points = {(row["east_km"], row["north_km"]): row["scores"] for row in grid["points"]}
    half = grid["box_width_km"] / 2
    positions = tuple(-half + 2 * half * i / 8 for i in range(9))
    coarse = tuple(product(positions, repeat=2))
    zoom = grid["local_half_width_km"]
    offsets = tuple(-zoom + 2 * zoom * i / 6 for i in range(7))
    expected = set(coarse)
    for x, y in grid["endpoints"].values():
        expected.update((x + dx, y + dy) for dx, dy in product(offsets, repeat=2))
    if (not grid["complete"] or grid["evaluated_points"] != grid["planned_points"] or len(points) != 179
            or (grid["coarse_size"], grid["local_size"]) != (9, 7) or set(points) != expected
            or any(row["failures"] for row in grid["points"])
            or any(v is None or not isfinite(v) for row in points.values() for v in row.values())):
        raise ValueError("Expected the full standard coarse and endpoint-centered matched-c grid")
    endpoints = {arm: points[tuple(grid["endpoints"][arm])][arm] for arm in ARMS}
    minima = {arm: min(points.items(), key=lambda item: item[1][arm]) for arm in ARMS}
    return dict(coordinates=grid["endpoints"], endpoint_scores=endpoints, minima=minima,
                fitted_minus_zero_endpoint_score=endpoints["fitted_c"] - endpoints["c0"],
                coarse_coordinates=coarse), points


def geographic(publication, truth):
    from tools.pipeline_eval.scoring import distance_km

    arms = publication["science"]["arms"]
    data = {}
    for arm in ARMS:
        row = arms[arm]
        if row["latlon"] is None or row.get("rf_rms_hz") is None:
            continue
        latitude, longitude = row["latlon"]
        rf = row["rf_rms_hz"]
        if not all(isfinite(val) for val in (latitude, longitude, rf)):
            raise ValueError("Nonfinite terminal position or RF residual")
        data[arm] = dict(latlon=row["latlon"], rf_rms_hz=rf, horizontal_error_km=distance_km(truth, row["latlon"]))
    if len(data) == 2:
        data["fitted_minus_zero"] = {key: data["fitted_c"][key] - data["c0"][key]
                                    for key in ("rf_rms_hz", "horizontal_error_km")}
    return data


def score(root):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from history_risk_0016_raw import roster
    from joint_publication import artifacts
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from prospective_0316_solver import inspect, owner_delta
    from raw_0016_best_score import STOCK_OWNERS, STOCK_OWNERS_SHA
    from tools.pipeline_eval.qualification.paired_publication import evidence, verify_v3_publication

    seal = root / "prediction-seal.json"
    admission, timing = read(root / "admission.json"), read(root / "clock.json")
    active = frozen_sources()
    scorer = Path(__file__).name
    if (read(seal) != output_seal(root) or admission["member_trial_sources"] not in
            (active, active | {scorer: PRE_SEAL_SCORER})):
        raise ValueError("Require the frozen trial source and sealed candidate products")
    context = CONTROL / "process-context.json"
    stock_seal = roster(CONTROL) | {context.name: digest(context)}
    if json.loads(checked(CONTROL / "prediction-seal.json", CONTROL_SEAL)) != stock_seal:
        raise ValueError("The installed full-20 ms control changed after its seal")
    stock_log = read(CONTROL / "stock-clock.json")
    stock_clock = stock_log["clock"] if "clock" in stock_log else stock_log
    stock_receipt = json.loads((CONTROL / "stock.stdout").read_text().splitlines()[-1])
    verify_v3_publication(STOCK, stock_receipt)
    stock = evidence(STOCK, stock_receipt, stock_clock["started_unix_ns"], read_only=True)
    prior = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
    if prior["receipt"]["terminal_sha256"] != stock_receipt["terminal_sha256"]:
        raise ValueError("Archived full-window owners do not bind the actual installed terminal")
    owner_rows = prior["selected_rows"]
    for arm, rows in owner_rows.items():
        if canonical_digest({row[0]: row[1] for row in rows}) != stock["owners"][arm]:
            raise ValueError("Published baseline owner digest differs from the ordered receipt")
    truth = reference()
    estimates = dict(installed=geographic(dict(science=stock), truth))
    clocks = {}
    for metric in ("elapsed_s", "cpu_s"):
        prep = admission["setup"][metric] + admission["smoke"]["clock"][metric]
        clocks[metric] = dict(candidate_saved_child=timing[metric], candidate_setup=prep,
                              candidate_saved_charged=timing[metric] + prep, historical_raw_installed=stock_clock[metric])
    result = dict(case=CASE, passed=False, candidate_children=1, process=timing, clocks=clocks,
                  status="failed_child" if timing["exit_code"] else "scored", admission=admission,
                  scorer_sha256=active[scorer], sealed_scorer_sha256=admission["member_trial_sources"][scorer],
                  seal_sha256=digest(seal), estimates=estimates, reference_sha256=REFERENCE_PIN, installed=stock,
                  installed_figures=artifacts(STOCK, stock_receipt)["images"])
    if timing["exit_code"]:
        write(root / "result.json", result)
        return
    directory = root / "candidate"
    request = read(root / "request.json")
    receipt = read(directory / "worker.json")["receipt"]
    planned = admission["acquisition"]
    skips = planned["full"]["visits"] - planned["retained"]["visits"]
    try:
        candidate = inspect(directory, "alternate original compressed members", receipt, timing, request,
                            native_sha=admission["derived_packet_sha256"], windows=planned["full"]["visits"],
                            admitted=planned["retained"]["processed_visits"], audit_name="worker.json",
                            input_description=DESCRIPTION)
        counts = receipt["counts"]
        if (counts != dict(processed=planned["retained"]["processed_visits"],
                           invalid_capture=planned["retained"]["invalid_capture"], skipped_acquisition=skips,
                           skipped_fast_score=0) or receipt["region"] != stock_receipt["region"]):
            raise ValueError("The private receipt relabeled an absent acquisition or changed the offer")
        estimates["candidate"] = geographic(candidate, truth)
        owner_changes = {arm: owner_delta(rows, candidate["selected_rows"].get(arm, [])) for arm, rows in owner_rows.items()}
        result.update(candidate=candidate, owner_changes=owner_changes)
        if receipt["decision"] != "complete":
            write(root / "result.json", result | {"status": "withheld"})
            return
        grid = {}
        points = {}
        for label, folder, run in (("installed", STOCK, stock_receipt), ("candidate", directory, receipt)):
            store = FastStandardAnalysisStore(folder)
            grid[label], points[label] = grid_summary(store.position_grid(run["run_id"]))
        common = points["candidate"].keys() & points["installed"].keys()
        if len(common) < 81 or grid["candidate"]["coarse_coordinates"] != grid["installed"]["coarse_coordinates"]:
            raise ValueError("The original common coarse grid coordinate set changed")
        if not all(arm in estimates["candidate"] for arm in ARMS):
            raise ValueError("The candidate lacks an arm's finite location or RF fit")
        deltas = {arm: estimates["candidate"][arm]["horizontal_error_km"] - estimates["installed"][arm]["horizontal_error_km"]
                  for arm in ARMS}
        passes = all(delta <= LIMIT_KM for delta in deltas.values())
        grid_deltas = {arm: max(abs(points["candidate"][xy][arm] - points["installed"][xy][arm]) for xy in common)
                       for arm in ARMS}
        result.update(passed=passes, status="passed" if passes else "failed_accuracy", grid=grid,
                      common_grid_positions=len(common), common_max_abs_score_delta=grid_deltas,
                      position_error_delta_km=deltas)
    except (KeyError, ValueError) as error:
        result.update(status="failed_evidence", evidence_error=str(error))
    write(root / "result.json", result)


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    score(parser.parse_args().root)
