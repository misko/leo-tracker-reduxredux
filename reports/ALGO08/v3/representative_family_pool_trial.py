"""Saved-only full numerical evidence for the representative catalogue pool."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, solve, write


HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "measurements/track-quadrature.json.gz"
FIRST_POOL = HERE / "measurements/representative-family-pool.json.gz"
CASES = ("DS30-0008", "south-containing", "south-far")


def run(case, output, *, closure=False):
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_route import make_route
    if closure:
        from family_pool_closure import propose
    else:
        from representative_family_pool import propose

    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared Gauss slot with one numerical thread")
    native, archive, offer, expected, identity = inputs(case)
    if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
        raise ValueError("Original saved detections differ from the installed receiver")
    original = algo08_position.solve
    attempts, fallback, rows = [], [], {}

    def observed(native, reader, assets, offer):
        full = make_route(v5_core.infer, reader, fallback, repair=True, signed_finish=True)
        candidate = make_route(full, reader, attempts, repair=True, signed_finish=True, joint_proposal=propose)
        with patch.object(v5_core, "infer", candidate):
            decision, packet, policy = original(native, reader, assets, offer)
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("Returned position lacks its full standard numerical grid")
            rows.update({arm: [[r["observation_id"], r["norad"], r["role"]] for r in packet["rows"][arm]] for arm in ARMS})
        return decision, packet, policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offer)
    if len(attempts) != 1 or len(fallback) != int(attempts[0]["decision"] == "fallback"):
        raise ValueError("Expected one checked attempt at each used route")
    if fallback and fallback[0]["decision"] == "fallback":
        for key in ("arms", "owners", "reason", "status", "orbit_policy", "science"):
            if result.get(key) != expected.get(key):
                raise ValueError(f"Installed fallback changed archived {key}")
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Original causal archive changed")
    result.pop("owner_rows", None)
    names = ("representative_family_pool.py", "representative_family_pool_trial.py", "blind_joint_finish.py",
             "blind_joint_repair.py", "blind_joint_signed.py", "blind_joint_route.py")
    if closure:
        names += ("family_pool_closure.py",)
    result.update(case=case, identity=identity, host=host, attempt=attempts[0], fallback=fallback,
                  selected_rows=rows, closure_enabled=closure,
                  source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in names})
    write(output, result)


def score(directory, summary, full):
    from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
    from mixture_score import section
    from signed_0374_transfer import owner_changes

    paths = {case: directory / f"{case}.json" for case in CASES}
    sealed = {case: read(path) for case, path in paths.items()}
    with gzip.open(REFERENCE, "rt") as stream:
        controls = json.load(stream)["runs"]
    first_pool = None
    if all(result.get("closure_enabled") for result in sealed.values()):
        with gzip.open(FIRST_POOL, "rt") as stream:
            first_pool = json.load(stream)["cases"]
    for case, result in sealed.items():
        stock, signed = (controls[case][k] for k in ("stock", "signed-full"))
        if result["identity"] != stock["identity"] or result["identity"] != signed["identity"]:
            raise ValueError(f"The matched stage timing controls have different input provenance for {case}")
        if first_pool is not None and result["identity"] != first_pool[case]["identity"]:
            raise ValueError(f"The first pool control has a different causal input for {case}")
        if result["fallback"] and result["fallback"][0]["decision"] != "fallback":
            for key in ("arms", "owners", "science", "status", "reason"):
                if result.get(key) != signed.get(key):
                    raise ValueError(f"Full-catalogue fallback changed measured signed control {key}")
    truth = references()
    numbers = {}
    for case, result in sealed.items():
        stock, signed = (controls[case][k] for k in ("stock", "signed-full"))
        attempt = result["attempt"]
        fit = {name: section(result["arms"], truth[case], base["arms"])
               for name, base in (("stock", stock), ("signed-full", signed))}
        contained = face_clearance_km(result["identity"]["offer"], truth[case]) >= 0.
        direct = attempt["decision"] == "complete" and all(
            a["delta_error_km"] is not None and a["delta_error_km"] <= .25 for s in fit.values() for a in s["arms"].values()
        ) if contained else attempt["decision"] == "withheld"
        clocks = {k: v for k, v in attempt.items() if k.endswith("_clocks")}
        numbers[case] = dict(result={k: result.get(k) for k in ("status", "reason", "cpu_s", "elapsed_s", "objective_replay",
                                                               "grid_points", "associated")}, route=attempt["decision"],
                             route_reason=attempt.get("reason"), full_fallback=[step["decision"] for step in result["fallback"]],
                             signed_status=attempt.get("signed", {}).get("status"), pooled_times=clocks,
                             pool=attempt.get("family_pool"), pooled_salvage=attempt.get("pooled_salvage"),
                             contained=contained, direct_quality_pass=direct, target_24_cpu_s=result["cpu_s"] < 24.,
                             versus=fit, stock_fit=section(stock["arms"], truth[case], stock["arms"]),
                             full_signed_fit=section(signed["arms"], truth[case], stock["arms"]),
                             stock_cpu_s=stock["cpu_s"], full_signed_cpu_s=signed["cpu_s"],
                             owner_changes={name: owner_changes(dict(selected_rows=base.get("selected_rows", {})), result)
                                            for name, base in (("stock", stock), ("signed-full", signed))})
        if first_pool is not None:
            previous = first_pool[case]
            numbers[case].update(closure=attempt["pool_closure"], first_pool_cpu_s=previous["cpu_s"],
                                 first_pool_route=previous["attempt"]["decision"],
                                 first_pool_cold_reason=previous["attempt"].get("reason"))
    pins = dict(trials={case: sha256(path.read_bytes()).hexdigest() for case, path in paths.items()},
                comparator_archive=sha256(REFERENCE.read_bytes()).hexdigest(),
                references={p.name: sha256(p.read_bytes()).hexdigest() for p in (PHYSICAL, SIMULATED)})
    if first_pool is not None:
        pins["first_pool_archive"] = sha256(FIRST_POOL.read_bytes()).hexdigest()
    write(summary, dict(cases=numbers, verification=pins))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(cases=sealed, scores=numbers, verification=pins),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("case", choices=CASES)
    trial.add_argument("output", type=Path)
    trial.add_argument("--closure", action="store_true")
    scoring = actions.add_parser("score")
    for name in ("directory", "summary", "full"):
        scoring.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    action = args.pop("action")
    (run if action == "run" else score)(**args)
