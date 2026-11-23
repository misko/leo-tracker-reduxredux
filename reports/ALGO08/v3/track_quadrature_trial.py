"""Charge a track-quadrature proposal through the original full numerical evidence."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, solve, write


CASES = ("DS30-0008", "south-containing", "south-far")
MODES = ("stock", "signed-full", "quadrature")
HERE = Path(__file__).resolve().parent


def trial(case, mode, output):
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_route import make_route
    from track_quadrature import SAMPLER, propose

    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(n != "1" for n in system["threads"].values())):
        raise ValueError("Use the shared Gauss lock and one low-priority numerical core")
    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("Expected the released original detector packet")
    original = algo08_position.solve
    attempts, evidence = [], {}

    def observed(native, reader, assets, region):
        if mode == "stock":
            decision, packet, policy = original(native, reader, assets, region)
        else:
            route = make_route(v5_core.infer, reader, attempts, repair=True, signed_finish=True,
                               joint_proposal=propose if mode == "quadrature" else None)
            with patch.object(v5_core, "infer", route):
                decision, packet, policy = original(native, reader, assets, region)
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("A returned position lacked the original complete numerical grid")
            evidence["selected_rows"] = {arm: [[r["observation_id"], r["norad"], r["role"]] for r in packet["rows"][arm]]
                                         for arm in ARMS}
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offer)
    if mode == "stock" or (attempts and attempts[-1]["decision"] == "fallback"):
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if result.get(key) != expected.get(key):
                raise ValueError(f"Full installed solver changed archived {key}")
    if archive_identity(archive) != identity["archive"] or len(attempts) != int(mode != "stock"):
        raise ValueError("Causal archive or number of route attempts changed")
    paths = (Path(__file__), SAMPLER, *(HERE / name for name in ("track_quadrature.py", "blind_joint_finish.py",
             "blind_joint_route.py", "blind_joint_repair.py", "blind_joint_signed.py")))
    result.pop("owner_rows", None)  # The ID and role witness below suffices.
    result.update(identity=identity, mode=mode, machine=system, attempts=attempts,
                  source_sha256={path.name: sha256(path.read_bytes()).hexdigest() for path in paths}, **evidence)
    write(output, result)


def score(directory, summary, full):
    from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
    from mixture_score import section
    from signed_0374_transfer import owner_changes

    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in MODES} for case in CASES}
    sealed = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    for case, modes in sealed.items():
        stock = modes["stock"]
        for mode, result in modes.items():
            if (result["identity"] != stock["identity"] or result["source_sha256"] != stock["source_sha256"]
                    or result["identity"]["case"] != case or result["mode"] != mode):
                raise ValueError("Paired modes changed source, capture or offer")
    truth = references()
    cases = {}
    for case, modes in sealed.items():
        stock, signed, candidate = (modes[method] for method in MODES)
        attempt, = candidate["attempts"]
        contained = face_clearance_km(candidate["identity"]["offer"], truth[case]) >= 0
        decision = attempt["decision"]
        versus = {name: section(candidate["arms"], truth[case], base["arms"])
                  for name, base in (("stock", stock), ("signed-full", signed))}
        accepted = (decision == "complete" and all(
            record["delta_error_km"] is not None and record["delta_error_km"] <= .25
            for comparison in versus.values() for record in comparison["arms"].values())
                    if contained else decision == "withheld")
        results = {}
        for mode, result in modes.items():
            route = (result["attempts"] or [{}])[0]
            results[mode] = dict(
                **{k: result.get(k) for k in ("cpu_s", "elapsed_s", "status", "reason", "grid_points", "objective_replay",
                                              "associated", "input_observations")},
                scoring=section(result["arms"], truth[case], stock["arms"]), route=route.get("decision", "stock"),
                route_reason=route.get("reason"), signed_status=route.get("signed", {}).get("status"),
                proposal=route.get("quadrature"), repair=route.get("repair"),
                clocks={k: v for k, v in route.items() if k.endswith("_clocks")},
                selected_roles={arm: {role: sum(r[2] == role for r in rows) for role in ("conditional", "predictive")}
                                for arm, rows in result.get("selected_rows", {}).items()},
            )
        cases[case] = dict(contained=contained, triage_pass=accepted, matches=results,
                           dense_budget_pass=candidate["cpu_s"] <= 24. if case == "DS30-0008" else None,
                           versus=versus,
                           ownership={mode: owner_changes(dict(selected_rows=modes[mode].get("selected_rows", {})),
                                                          dict(selected_rows=candidate.get("selected_rows", {})))
                                      for mode in MODES[:2]})
    binding = dict(files={path.name: sha256(path.read_bytes()).hexdigest() for modes in paths.values() for path in modes.values()},
                   references={path.name: sha256(path.read_bytes()).hexdigest() for path in (PHYSICAL, SIMULATED)})
    write(summary, dict(verification=binding, cases=cases))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(verification=binding, runs=sealed, scores=cases),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    running = actions.add_parser("run")
    running.add_argument("case", choices=CASES)
    running.add_argument("mode", choices=MODES)
    running.add_argument("output", type=Path)
    scoring = actions.add_parser("score")
    for key in ("directory", "summary", "full"):
        scoring.add_argument(key, type=Path)
    args = vars(parser.parse_args())
    action = args.pop("action")
    (trial if action == "run" else score)(**args)


if __name__ == "__main__":
    main()
