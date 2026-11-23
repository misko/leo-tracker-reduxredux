"""Replay exact full-catalogue cold starts with and without contrast pruning."""

import argparse
from collections import Counter
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
import runpy
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, inputs, machine, read, solve, write
from paid_certified_trial import prepare, sealed


HERE = Path(__file__).resolve().parent
SHARED_RANK = HERE.parents[2] / "tools/pipeline_eval/variants/algo08_blind_rank.py"
CASES = ("DS30-0016", "DS30-0008", "south-containing", "south-far")
PRIMARY = CASES[:2]
MODES = ("control", "contrast")


def run(case, mode, output, *, paid_south=False):
    if paid_south and (case not in ("south-containing", "south-far") or mode != "control"):
        raise ValueError("Paid southern transfer requires a southern offer and the original full nominations")
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared Gauss slot with one numerical thread")
    publication, spec = configuration()
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_finish import cold_candidate, elapsed
    from blind_joint_route import make_route
    from certified_salvage import propose
    from lighter_joint_estimator import update
    from paid_quadratic import quadratic
    from representative_contrast_bound import bounded_nominations

    shared_rank = runpy.run_path(str(SHARED_RANK))["shared_rank_preparation"]
    paid = case == "DS30-0016" or paid_south
    if paid:
        native, archive, offer, identity = prepare(case, "quadratic")
    else:
        native, archive, offer, _, identity = inputs(case)
        if identity["detector_sha256"] != "sha256:" + spec["detector_sha256"]:
            raise ValueError("Saved detector specification changed")
    original, config = algo08_position.solve, algo08_position.TrackConfig
    attempts, ranks, chosen, rows = [], [], [], {}

    def cold(prepared, region, bound):
        installed = v5_core.ranked_initial_nodes

        def rank(scan):
            cpu, wall = process_time(), perf_counter()
            counts = Counter()
            with shared_rank(scan) as shared, bounded_nominations(scan, counts, enabled=mode == "contrast"):
                cold_nodes = installed(scan)
            ranks.append(dict(clocks=elapsed(cpu, wall), roster=len(scan.norads),
                              tracks=len(scan.curved), shared=shared, counts=counts, nodes=cold_nodes))
            return cold_nodes

        with patch.object(v5_core, "ranked_initial_nodes", rank):
            node, point, phases, details = cold_candidate(prepared, region, bound)
        chosen.append(dict(node=node, point=point, phases=phases, details=details))
        return node, point, phases, details

    def observed(document, reader, assets, supplied):
        proposal = partial(propose, certified=True, cold_start=cold)
        candidate = make_route(v5_core.infer, reader, attempts, repair=True, signed_finish=True,
                               joint_proposal=proposal, signed_updater=update)
        factory = (lambda **values: quadratic(config(**values))) if paid else config
        with patch.object(v5_core, "infer", candidate), patch.object(algo08_position, "TrackConfig", factory):
            decision, packet, orbit_policy = original(document, reader, assets, supplied)
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("Returned position lacks the full numerical grid")
            rows.update({arm: [[r["observation_id"], r["norad"], r["role"]] for r in packet["rows"][arm]] for arm in ARMS})
        return decision, packet, orbit_policy

    with patch.object(algo08_position, "solve", observed):
        result = solve(publication, spec, native, archive, offer)
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the saved fit")

    def digest(value):
        return canonical_digest(json.loads(json.dumps(value, default=_json_value)))

    for rank in ranks:
        nodes = rank.pop("nodes")
        rank["ordered_nodes_sha256"] = digest(nodes)
        rank["hypotheses"] = len(nodes)
        rank["all_norad_alias_sha256"] = digest([[(r["candidate_norad"], a) for r, a in
                                               zip(n["seed"]["rows"], n["aliases"], strict=True)] for n in nodes])
    for winner in chosen:
        winner["node_sha256"] = digest(winner.pop("node"))
    result.pop("owner_rows", None)
    names = ("full_family_amortized_trial.py", "representative_contrast_bound.py", "full-family-amortized-protocol.md",
             "certified_salvage.py", "lighter_joint_estimator.py")
    source = {name: sha256((HERE / name).read_bytes()).hexdigest() for name in names}
    source[SHARED_RANK.name] = sha256(SHARED_RANK.read_bytes()).hexdigest()
    result.update(identity=identity, mode=mode, host=host, attempts=attempts, ranks=ranks, chosen=chosen,
                  selected_rows=rows, source_sha256=source)
    write(output, result)


def equality(control, contrast):
    keys = ("arms", "owners", "selected_rows", "science", "grid_points", "objective_replay", "status", "reason", "chosen")
    same = {key: control.get(key) == contrast.get(key) for key in keys}
    rkeys = ("ordered_nodes_sha256", "all_norad_alias_sha256", "hypotheses", "roster", "tracks")
    same["ordered_rank"] = ([{k: r[k] for k in rkeys} for r in control["ranks"]]
                            == [{k: r[k] for k in rkeys} for r in contrast["ranks"]])
    akeys = ("support", "finish", "signed", "decision", "reason", "exterior")
    same["validation"] = ([{k: a.get(k) for k in akeys} for a in control["attempts"]]
                          == [{k: a.get(k) for k in akeys} for a in contrast["attempts"]])
    return same


def score(directory, summary, full, *, include_south=False):
    from aperture_score import PHYSICAL, SIMULATED, references
    from mixture_score import section

    cases = CASES if include_south else PRIMARY
    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in MODES} for case in cases}
    runs = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    checks = {}
    for case, rows in runs.items():
        if rows["control"]["identity"]["native_sha256"] != rows["contrast"]["identity"]["native_sha256"]:
            raise ValueError("Exact rank arms used different inputs")
        checks[case] = equality(rows["control"], rows["contrast"])
    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == "DS30-0016" and r["authority_eligible"]]
    truth["DS30-0016"] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    previous = sealed("installed")
    with gzip.open(HERE / "measurements/certified-salvage.json.gz", "rt") as stream:
        pooled = json.load(stream)["cases"]
    paid = sealed("quadratic")["DS30-0016"]["quadratic"]
    with gzip.open(HERE / "measurements/paid-certified.json.gz", "rt") as stream:
        paid_pool = json.load(stream)["runs"]["DS30-0016"]["quadratic"]

    results = {}
    for case, rows in runs.items():
        paid_case = case == "DS30-0016"
        references_by_route = ({"old_full_signed": paid["result"], "certified_pool": paid_pool} if paid_case else
                               {"old_full_signed": previous[case]["signed-full"], "installed": previous[case]["stock"],
                                "certified_pool": pooled[case]})
        if paid_case:
            references_by_route["old_full_signed"] = dict(paid["result"], cpu_s=paid["charged"]["cpu_s"])
        for compared in references_by_route.values():
            if compared.get("identity", rows["control"]["identity"])["native_sha256"] != rows["control"]["identity"]["native_sha256"]:
                raise ValueError("Archived comparison packet differs")
        result = {}
        for mode, row in rows.items():
            result[mode] = dict(cpu_s=row["cpu_s"], elapsed_s=row["elapsed_s"], status=row["status"],
                                reason=row["reason"], associated=row.get("associated"), grid_points=row.get("grid_points"),
                                rank=row["ranks"], clocks=[{k: v for k, v in a.items() if k.endswith("_clocks")} for a in row["attempts"]],
                                decision=[(a.get("decision"), a.get("reason"), a.get("signed", {}).get("status")) for a in row["attempts"]],
                                versus={k: dict(cpu_s=b.get("cpu_s"), **section(row["arms"], truth[case], b["arms"]))
                                        for k, b in references_by_route.items()})
        result["exact_pair"] = checks[case]
        results[case] = result
    validation = {p.name: sha256(p.read_bytes()).hexdigest() for modes in paths.values() for p in modes.values()}
    write(summary, dict(cases=results, verification=validation))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(runs=runs, scores=results, verification=validation),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("case", choices=CASES)
    trial.add_argument("mode", choices=MODES)
    trial.add_argument("output", type=Path)
    trial.add_argument("--paid-south", action="store_true")
    scorer = actions.add_parser("score")
    for name in ("directory", "summary", "full"):
        scorer.add_argument(name, type=Path)
    scorer.add_argument("--include-south", action="store_true")
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
