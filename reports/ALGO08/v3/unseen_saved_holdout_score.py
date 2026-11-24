"""Verify both sealed DS30-0255 products before joining held-out positions."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from unseen_saved_holdout import ADMITTED, CASE, ISSUED, NATIVE_PIN, PANEL, ROOT, digest, enrollment, runtime_sources


ARMS = ("c0", "fitted_c")
REFERENCE_PIN = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"


def read(path):
    return json.loads(path.read_bytes())


def reference():
    body = subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
                                    "2d0ad2dfd:reports/2026_11_21_ds30_full/reference-audit.json"])
    if digest(body) != REFERENCE_PIN:
        raise ValueError("The holdout's archived reference changed")
    (case,) = (row for row in json.loads(body)["cases"] if row["dataset_label"] == CASE
               and row["authority_eligible"] and row["sealed_metadata_digests_verified"])
    return [case["reference"][key] for key in ("latitude_deg", "longitude_deg")]


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from history_risk_residual_layout_0402 import media_identity
    from prospective_0316_solver import inspect, owner_delta
    from tools.pipeline_eval.scoring import distance_km

    book = read(root / "admission.json")
    if (read(root / "prediction-seal.json") != output_seal(root) or book["sources"] != runtime_sources()
            or book["assignment"] != json.loads(json.dumps(enrollment()))
            or book["job_sha256"] != digest((root / "job.json").read_bytes())):
        raise ValueError("The held-out assignment, runtime or signed outputs changed")
    original = json.loads(checked(PANEL / "pair.json", book["assignment"]["archived_pair_sha256"]))["runs"]["candidate"]
    request = read(root / "request.json")
    jobs = {}
    for mode in book["assignment"]["order"]:
        root_mode = root / mode
        clock = read(root_mode / "clock.json")
        if clock["exit_code"]:
            jobs[mode] = dict(clock=clock, decision="failed", publication=None)
            continue
        folder = root_mode / "candidate"
        receipt = read(folder / "worker.json")["receipt"]
        products = inspect(folder, mode, receipt, clock, request, native_sha=NATIVE_PIN,
                           windows=ISSUED, admitted=ADMITTED, audit_name="worker.json")
        jobs[mode] = dict(clock=clock, decision=receipt["decision"], publication=products)
    named, routed = (jobs[mode] for mode in ("installed", "routed"))
    check, owners, media, sides = {}, None, None, None
    if named["publication"]:
        baseline = named["publication"]["science"]
        check["installed_signed_terminal"] = (
            baseline["receipt"]["terminal_sha256"] == original["receipt"]["terminal_sha256"])
        check["installed_original_owners"] = baseline["owners"] == original["owners"]
        check["installed_original_arms"] = baseline["arms"] == original["arms"]
    if named["publication"] and routed["publication"]:
        before, after = (jobs[mode]["publication"] for mode in ("installed", "routed"))
        check["same_input_and_offer"] = all(before["terminal"][k] == after["terminal"][k]
                                             for k in ("native_sha256", "region", "session_id"))
        check["equal_decision"] = named["decision"] == routed["decision"]
        check["equal_terminal"] = before["terminal"] == after["terminal"]
        owners = {arm: owner_delta(before["selected_rows"][arm], after["selected_rows"][arm]) for arm in ARMS}
        if named["decision"] == routed["decision"] == "complete":
            base_media, new_media = (media_identity(pub["figures"]) for pub in (before, after))
            media = {name: base_media[name] == new_media[name] for name in base_media}
            sides = {name: before["sidecars"][name]["scientific_sha256"] == after["sidecars"][name]["scientific_sha256"]
                     for name in ("grid", "path")}
    truth = reference()
    geographic = {}
    for mode, job in jobs.items():
        arms = job["publication"]["science"]["arms"] if job["publication"] else {}
        geographic[mode] = {arm: dict(horizontal_error_km=distance_km(truth, row["latlon"]), rf_rms_hz=row["rf_rms_hz"])
                            if (row := arms.get(arm)) and row["latlon"] else None for arm in ARMS}
    candidate_delta_m = {arm: (
        1000*(geographic["routed"][arm]["horizontal_error_km"]-geographic["installed"][arm]["horizontal_error_km"])
        if geographic["routed"][arm] and geographic["installed"][arm] else None) for arm in ARMS}
    time = {metric: dict(
        installed=named["clock"][metric], routed=routed["clock"][metric],
        routed_div_installed=routed["clock"][metric]/named["clock"][metric])
        for metric in ("elapsed_s", "cpu_s")}
    wake = root / "routed"
    traces = {name: read(wake / name) for name in ("risk-route.json", "render-usage.json", "live-corner.json")
              if (wake / name).is_file()}
    if (wake / "candidate/ports.json").is_file():
        traces["ports"] = read(wake / "candidate/ports.json")
    write(root / "result.json", dict(
        case=CASE, admission=book, jobs=jobs, checks=check, geographic=geographic, owner_changes=owners,
        media_equal=media, numerical_sidecars_equal=sides, candidate_minus_installed_horizontal_m=candidate_delta_m,
        time=time, candidate_traces=traces, prior_installed_raw={key:original[key] for key in ("elapsed_s", "cpu_s")},
        reference_sha256=REFERENCE_PIN, original_waveform_reads=0, saved_children=2,
        prediction_seal_sha256=digest((root / "prediction-seal.json").read_bytes())))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
