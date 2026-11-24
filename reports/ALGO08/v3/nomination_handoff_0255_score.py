"""Verify the sealed post-holdout run against both original saved clocks."""

import argparse
import json
from pathlib import Path
import sys

from nomination_handoff_0255 import BASE, BASE_PIN, saved
from nomination_handoff_0255_publication import remediation_pins
from unseen_saved_holdout import ADMITTED, ISSUED, NATIVE_PIN, ROOT, digest


def read(path):
    return json.loads(path.read_bytes())


def score(root):
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from history_risk_residual_layout_0402 import media_identity
    from prospective_0316_solver import inspect
    from publication_media_checks import verify_position_sidecars

    book, clock = (read(root / key) for key in ("admission.json", "clock.json"))
    prior = saved()
    if (read(root / "prediction-seal.json") != output_seal(root) or book["source_pins"] != remediation_pins()
            or book["original_holdout_sha256"] != BASE_PIN
            or book["job_sha256"] != prior["admission"]["job_sha256"]):
        raise ValueError("The original holdout pairing or new sealed products changed")
    base = prior["jobs"]
    receipt = dict(stage="post-holdout", admission=book, clock=clock, candidate_children=1,
                   controls={key: row["clock"] for key, row in base.items()},
                   prediction_seal_sha256=digest((root / "prediction-seal.json").read_bytes()),
                   original_pair_receipt=BASE_PIN, original_waveform_reads=0)
    if clock["exit_code"]:
        write(root / "result.json", receipt | {"qualified": False, "reason": "candidate failed"})
        return
    folder = root / "routed/candidate"
    worker = read(folder / "worker.json")
    observed = inspect(folder, "routed", worker["receipt"], clock, read(BASE / "request.json"),
                       native_sha=NATIVE_PIN, windows=ISSUED, admitted=ADMITTED, audit_name="worker.json")
    old = base["routed"]["publication"]
    risk = read(root / "routed/risk-route.json")
    (trace,) = risk["solves"]
    old_trace = prior["candidate_traces"]["risk-route.json"]["solves"][0]
    live = trace["nomination_handoff"]
    (new_try,) = trace["lean_attempts"]
    (old_try,) = old_trace["lean_attempts"]
    checks = dict(
        actual_consumer=(live.get("scan_reuses"), live.get("rank_reuses"), live.get("prefixes_reused")) == (1, 1, 3),
        same_repair_refusal=all(new_try[key] == old_try[key] for key in ("decision", "reason", "pair_passes", "repair")),
        same_terminal=observed["terminal"] == old["terminal"] == base["installed"]["publication"]["terminal"],
        same_arms=observed["science"]["arms"] == old["science"]["arms"],
        same_ordered_owners=observed["selected_rows"] == old["selected_rows"]
        and observed["science"]["owners"] == old["science"]["owners"],
        all_eight_exact_pngs=media_identity(observed["figures"]) == media_identity(old["figures"])
        and len(observed["figures"]) == 8,
    )
    comparisons = verify_position_sidecars(BASE / "routed/candidate", folder, worker["receipt"]["run_id"],
                                               old["figures"], observed["figures"])
    clocks = {metric: dict(remediation=clock[metric], delta_to_original_routed=clock[metric] - base["routed"]["clock"][metric],
                           delta_to_fresh_named=clock[metric] - base["installed"]["clock"][metric])
              for metric in ("elapsed_s", "cpu_s")}
    write(root / "result.json", receipt | dict(qualified=all(checks.values()), checks=checks, scope=clocks,
          risk=risk, publication=observed, sidecars=comparisons, original_geographic=prior["geographic"],
          ports=read(folder / "ports.json"), live_orbit=read(root / "routed/live-corner.json")))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
