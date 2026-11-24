"""Score the one sealed DS30-0129 transfer and its differently scoped controls."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from solver_exception_0129 import ADMITTED, CASE, HERE, ISSUED, NATIVE_PIN, PAIR_PIN, PANEL, ROOT, digest, runtime_pins


def read(path):
    return json.loads(path.read_bytes())


def archived_blob(ref):
    return subprocess.check_output(["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT), "show", ref])


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from prospective_0316_solver import inspect
    from tools.pipeline_eval.scoring import distance_km

    admission, clock = (read(root / name) for name in ("admission.json", "clock.json"))
    if (read(root / "prediction-seal.json") != output_seal(root)
            or admission["source_pins"] != runtime_pins()
            or admission["job_sha256"] != digest((root / "job.json").read_bytes())):
        raise ValueError("The frozen worker, source inputs or outputs changed")
    pair = json.loads(checked(PANEL / "pair.json", PAIR_PIN))
    deployed, failure = pair["runs"]["baseline"], pair["runs"]["candidate"]
    stage = root / "routed"
    output = stage / "candidate"
    common = dict(case=CASE, admission=admission, clock=clock, paid_saved_children=1, original_reads=0,
                  archived_v3={key: failure[key] for key in ("elapsed_s", "cpu_s", "native_sha256")},
                  prior_exception=failure["failure_observation"]["stderr"].splitlines()[-1],
                  support=read(stage / "live-corner.json"),
                  prediction_seal_sha256=digest((root / "prediction-seal.json").read_bytes()))
    if clock["exit_code"]:
        write(root / "result.json", common | dict(complete=False, reason="candidate failed"))
        return
    req = read(root / "request.json")
    receipt = read(output / "worker.json")["receipt"]
    active = inspect(output, "0129 in-flight", receipt, clock, req, native_sha=NATIVE_PIN,
                     windows=ISSUED, admitted=ADMITTED, audit_name="worker.json")
    if receipt["decision"] != "complete":
        write(root / "result.json", common | dict(complete=False, publication=active, reason="candidate withheld"))
        return
    original_repair = archived_blob(
        "2a74c3a5c:reports/ALGO08/single-core-2x/measurements/algo08v3-DS30-0129-orbit-support-saved.json")
    old = json.loads(original_repair)
    reference = archived_blob("9b8018cc4:reports/2026_11_21_ds30_full/reference-audit.json")
    reference_pin = "c055e43a03d22379c0bde7e136cb786efae1fe6a31919cc1e3ecea32637840b5"
    if (digest(reference) != reference_pin or old["verification"]["source_digest"] != "sha256:" + NATIVE_PIN
            or old["verification"]["archive_digest"] != pair["archive"]["snapshots_sha256"]
            or not old["verification"]["identical_probe_rows"]):
        raise ValueError("The archived comparison does not bind the same signed original input")
    (site,) = (r for r in json.loads(reference)["cases"] if r["dataset_label"] == CASE
               and r["authority_eligible"] and r["sealed_metadata_digests_verified"])
    truth = [site["reference"][x] for x in ("latitude_deg", "longitude_deg")]
    all_arms = {"fresh": active["science"]["arms"], "v2": deployed["arms"], "earlier_repair": old["arms"]}
    geo = {run: {arm: dict(horizontal_error_km=distance_km(truth, row["latlon"]), rf_rms_hz=row["rf_rms_hz"])
                 for arm, row in arms.items()} for run, arms in all_arms.items()}
    checks = dict(original_signed_offer=receipt["region"] == deployed["receipt"]["region"],
                  previous_exact_arms=active["science"]["arms"] == old["arms"],
                  previous_exact_owners=active["science"]["owners"] == old["owners"],
                  v2_exact_arms=active["science"]["arms"] == deployed["arms"],
                  v2_exact_owners=active["science"]["owners"] == deployed["owners"])
    roles = {arm: {kind: sum(row[2] == kind for row in rows) for kind in sorted({row[2] for row in rows})}
             for arm, rows in active["selected_rows"].items()}
    history = read(output / "ports.json")
    write(root / "result.json", common | dict(
        complete=True, comparisons=checks, publication=active, geographic=geo, roles=roles, ports=history,
        risk=read(stage / "risk-route.json"), renderer=read(stage / "render-usage.json"),
        archived_repair_sha256=digest(original_repair), reference_sha256=reference_pin,
        archived_v2_raw={key: deployed[key] for key in ("elapsed_s", "cpu_s", "owners", "arms")},
        archived_repair_numeric={key: old[key] for key in (
            "solver_wall_s", "solver_cpu_s", "orbit_extension", "associated", "owners", "arms")},
    ))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
