"""Run one sealed dense reassociation diagnostic without a redundant fallback."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, solve, write


HERE = Path(__file__).resolve().parent
PRIOR = HERE / "measurements/track-quadrature.json.gz"


def trial(output):
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from quadrature_local_repair import diagnose
    from track_quadrature import propose

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared one-core Gauss numerical slot")
    native, archive, offer, _, identity = inputs("DS30-0008")
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("Expected the original released receiver packet")
    original = algo08_position.solve
    measured = {}

    def compare(signed, region, _measured):
        measured["reassociation"] = diagnose(signed, region)
        return None, "sealed_local_reassociation_diagnostic"

    def diagnose_infer(prepared, region, bound, _stages, *, selected_evidence):
        result, reason = propose(prepared, region, bound, measured, repair=compare)
        if result is not None or reason != "sealed_local_reassociation_diagnostic":
            raise ValueError("Expected to observe the failed exact paired quadrature fit once")
        return dict(status="withheld", reason=reason, arms={arm: {"latlon": None} for arm in ARMS})

    def observed(*args, **kwargs):
        with patch.object(v5_core, "infer", diagnose_infer):
            return original(*args, **kwargs)

    with patch.object(algo08_position, "solve", observed):
        charged = solve(publication, spec, native, archive, offer)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Capture-era orbit archive changed")
    names = ("track_quadrature.py", "blind_joint_finish.py", "quadrature_local_repair.py",
             "quadrature_local_repair_trial.py")
    write(output, dict(identity=identity, host=host, measured=measured, charged=charged,
                       source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in names}))


def audit(path, output):
    diagnostic = read(path)
    with gzip.open(PRIOR, "rt") as stream:
        previous = json.load(stream)["runs"]["DS30-0008"]
    old = previous["quadrature"]["attempts"][0]
    measured = diagnostic["measured"]
    rf = measured["reassociation"]
    checks = dict(identity=previous["quadrature"]["identity"] == diagnostic["identity"],
                  support=old["quadrature"] == measured["quadrature"], ordinary_fit=old["finish"] == measured["finish"],
                  losses=old["repair"]["rejection_counts"] == rf["original_losses"])
    if not all(checks.values()):
        raise ValueError(f"Prior dense science changed: {checks}")
    reference = {arm: {row[0]: row[1:] for row in rows} for arm, rows in previous["stock"]["selected_rows"].items()}
    overlap = {}
    for key, target in rf["targets"].items():
        overlap[key] = {}
        for arm, owners in reference.items():
            choices = Counter(tuple(owners[oid]) for oid in target["observation_ids"] if oid in owners)
            overlap[key][arm] = dict(matched=sum(choices.values()),
                                     stock_owner_roles=[(owner, role, n) for (owner, role), n in choices.most_common()])
    full = previous["signed-full"]
    original_stages = full["attempts"][0]
    budget = 24.
    charged = diagnostic["charged"]["cpu_s"]
    direct_projection = charged + sum(original_stages[k]["cpu_s"] for k in
                                      ("signed_total_clocks", "exterior_clocks", "standard_evidence_clocks"))
    write(output, dict(checks=checks, diagnostic_sha256=sha256(path.read_bytes()).hexdigest(),
                       prior_sha256=sha256(PRIOR.read_bytes()).hexdigest(), stock_overlap=overlap,
                       timing=dict(diagnostic_cpu_s=charged, budget_cpu_s=budget, projected_direct_cpu_s=direct_projection,
                                   prior_rejected_pre_fallback_cpu_s=previous["quadrature"]["cpu_s"] - old["fallback_clocks"]["cpu_s"],
                                   prior_fallback_cpu_s=old["fallback_clocks"]["cpu_s"],
                                   fresh_stock_cpu_s=previous["stock"]["cpu_s"], full_signed_cpu_s=full["cpu_s"],
                                   full_cold_and_salvage_cpu_s=sum(original_stages[k]["cpu_s"] for k in ("cold_clocks", "salvage_clocks"))),
                       proceed=(rf.get("exact_pair", {}).get("status") == "qualified" and direct_projection <= budget)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run")
    run.add_argument("output", type=Path)
    check = sub.add_parser("audit")
    check.add_argument("path", type=Path)
    check.add_argument("output", type=Path)
    opts = vars(parser.parse_args())
    action = opts.pop("action")
    (trial if action == "run" else audit)(**opts)
