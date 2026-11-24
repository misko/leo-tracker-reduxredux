"""Verify the in-flight orbit result against the complete sealed original retry."""

import argparse
import json
from pathlib import Path
import sys

from solver_exception_0022 import ADMITTED, ISSUED, NATIVE_PIN, ROOT, digest
from solver_exception_live import PREVIOUS, PREVIOUS_PIN, sources


def read(path):
    return json.loads(path.read_bytes())


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from empty_bootstrap import checked
    from history_risk_residual_layout_0402 import media_identity
    from prospective_0316_solver import inspect
    from publication_media_checks import verify_position_sidecars

    book, clock = (read(root / name) for name in ("admission.json", "clock.json"))
    old = json.loads(checked(PREVIOUS / "result.json", PREVIOUS_PIN))
    if (read(root / "prediction-seal.json") != output_seal(root) or sources() != book["sources"]
            or book["job_sha256"] != old["admission"]["job_sha256"] or not old["qualified_recovery"]):
        raise ValueError("The prediction or authenticated prior comparison changed")
    stage = root / "routed"
    live = read(stage / "live-corner.json")
    result = dict(case="DS30-0022", candidate_clock=clock, baseline_clock=old["clock"],
                  baseline_setup=old["admission"]["setup_clock"], admission=book, support=live,
                  prediction_seal_sha256=digest((root / "prediction-seal.json").read_bytes()), saved_children=1,
                  no_waveform=True)
    if clock["exit_code"]:
        write(root / "result.json", result | {"qualified": False, "reason": "candidate failed"})
        return
    folder = stage / "candidate"
    req = read(PREVIOUS / "request.json")
    receipt = read(folder / "worker.json")["receipt"]
    observed = inspect(folder, "in-flight", receipt, clock, req, windows=ISSUED, admitted=ADMITTED,
                       native_sha=NATIVE_PIN, audit_name="worker.json")
    ordinary = old["published"]
    ports = read(folder / "ports.json")
    risk = read(stage / "risk-route.json")
    choices, = risk["solves"]
    earlier = old["risk"]["solves"][0]
    achieved = live["in_flight"]
    lines = ("corner_projections_extended", "sgp4_calls", "sgp4_state_count", "new_state_count", "added_knots_s")
    new_route = choices["lean_attempts"]
    old_route = earlier["lean_attempts"][-1]
    checks = dict(
        one_preparation_and_inference=len(ports["history"]["prepare"]) == len(ports["history"]["infer"]) == 1
        and all(ports["history"][key][0]["status"] == "returned" for key in ("prepare", "infer")),
        same_extension_without_restart=len(achieved) == 1 and not live["original_restart"]
        and all(achieved[0][key] == old["patched_retry"][0][key] for key in lines),
        unchanged_rejection_and_fallback=len(new_route) == 1 and choices["inference_calls"] == 1
        and all(new_route[0][k] == old_route[k] for k in ("decision", "reason", "repair", "pair_passes"))
        and all(choices["choice"][k] == earlier["choice"][k] for k in ("route", "reason")),
        exact_terminal=observed["terminal"] == ordinary["terminal"],
        exact_both_arms=observed["science"]["arms"] == ordinary["science"]["arms"],
        exact_ordered_owners=observed["selected_rows"] == ordinary["selected_rows"]
        and observed["science"]["owners"] == ordinary["science"]["owners"],
        same_scientific_authority=observed["science"]["raw_authority"] == ordinary["science"]["raw_authority"]
        and receipt["region"] == ordinary["worker"]["receipt"]["region"],
        exact_eight_pngs=media_identity(observed["figures"]) == media_identity(ordinary["figures"])
        and len(observed["figures"]) == 8,
    )
    current_sidecars = verify_position_sidecars(PREVIOUS / "routed/candidate", folder, receipt["run_id"],
                                               ordinary["figures"], observed["figures"])
    savings = {metric: old["clock"][metric] - clock[metric] for metric in ("elapsed_s", "cpu_s")}
    write(root / "result.json", result | dict(qualified=all(checks.values()), checks=checks,
          outputs=observed, risk=risk, ports=ports, original_verified_ports=old["actual_ports"]["history"],
          sidecars=current_sidecars, geographic=old["geography"], savings=savings,
          render=read(stage / "render-usage.json"), original_numeric_clock=ordinary["worker"]["solve"]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
