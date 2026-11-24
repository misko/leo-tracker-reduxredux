"""Score the sealed DS30-0022 publication without another solve."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from solver_exception_0022 import ADMITTED, CASE, HERE, ISSUED, NATIVE_PIN, PAIR_PIN, PANEL, ROOT, digest, sources


def read(path):
    return json.loads(path.read_bytes())


def archived_reference():
    command = ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show",
               "9b8018cc4:reports/2026_11_21_ds30_full/reference-audit.json"]
    data = subprocess.check_output(command)
    if digest(data) != "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5":
        raise ValueError("The original frozen scoring reference changed")
    (row,) = (row for row in json.loads(data)["cases"] if row["dataset_label"] == CASE)
    if not row["authority_eligible"] or not row["sealed_metadata_digests_verified"]:
        raise ValueError("The original operator reference does not cover the signed acquisition")
    return [row["reference"][name] for name in ("latitude_deg", "longitude_deg")]


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from prospective_0316_solver import inspect
    from tools.pipeline_eval.scoring import distance_km

    admission, process = (read(root / name) for name in ("admission.json", "clock.json"))
    if read(root / "prediction-seal.json") != output_seal(root) or admission["sources"] != sources():
        raise ValueError("The actual frozen worker or its outputs changed")
    req = read(root / "request.json")
    historical = json.loads(checked(PANEL / "pair.json", PAIR_PIN))
    previous = read(HERE / "measurements/full-short-orbit-transfer.json")
    original = historical["runs"]["baseline"]
    failed = historical["runs"]["candidate"]
    phase = root / "routed"
    result = dict(case=CASE, admission=admission, clock=process, raw_children=0, paid_saved_children=1,
                  run=read(root / "run.json"), patched_retry=read(phase / "corner-retry.json"),
                  last_release_exception=failed["failure_observation"]["stderr"].splitlines()[-1],
                  archived_v3={key: failed[key] for key in ("elapsed_s", "cpu_s", "native_sha256")},
                  prediction_seal_sha256=digest((root / "prediction-seal.json").read_bytes()))
    if process["exit_code"]:
        write(root / "result.json", result | {"qualified_recovery": False, "reason": "child_failed"})
        return
    folder = phase / "candidate"
    receipt = read(folder / "worker.json")["receipt"]
    observed = inspect(folder, "routed", receipt, process, req, native_sha=NATIVE_PIN,
                       windows=ISSUED, admitted=ADMITTED, audit_name="worker.json")
    if receipt["decision"] != "complete":
        write(root / "result.json", result | {"qualified_recovery": False, "published": observed})
        return
    route = read(phase / "risk-route.json")
    ports = read(folder / "ports.json")
    render = read(phase / "render-usage.json")
    roles = {arm: sorted(set(row[2] for row in rows)) for arm, rows in observed["selected_rows"].items()}
    parity = dict(original_v2_positions_and_conditional_rf=observed["science"]["arms"] == original["arms"],
                  original_v2_owners=observed["science"]["owners"] == original["owners"],
                  ordered_roles_equal_between_calibrations=observed["selected_rows"]["c0"] == observed["selected_rows"]["fitted_c"],
                  original_offer=receipt["region"] == original["receipt"]["region"],
                  actual_corner_repair=observed["terminal"]["orbit_policy"] == "orbit_support"
                  and bool(result["patched_retry"]),
                  guarded_renderer=render["native_residual_figures"] == 2
                  and render["position_figures"] == render["track_figures"] == 1
                  and sum(row["figures"] for row in render["ordinary_orbit_draws"]) == 4)
    truth = archived_reference()
    geography = {arm: dict(horizontal_km=distance_km(truth, values["latlon"]), rf_rms_hz=values["rf_rms_hz"])
                 for arm, values in observed["science"]["arms"].items()}
    write(root / "result.json", result | dict(
        qualified_recovery=all(parity.values()), parity=parity, geography=geography, published=observed,
        ordered_role_types=roles, render=render, actual_ports=ports, risk=route,
        archived_v2_raw={key: original[key] for key in ("arms", "owners", "elapsed_s", "cpu_s")},
        archived_quadratic_saved={key: previous[key] for key in ("process", "solve", "score", "owners")},
    ))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
