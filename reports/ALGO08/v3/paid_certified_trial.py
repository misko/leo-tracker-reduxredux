"""Compare one certified solver on matched complete and paid quadratic packets."""

import argparse
from functools import partial
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time
from unittest.mock import patch

from aperture_trial import ARMS, archive_identity, configuration, machine, read, solve, write
from paid_graph_trial import prepare_paid
from paid_quadratic import quadratic
from sparse_consensus_trial import CASES, bound_inputs


HERE = Path(__file__).resolve().parent
MODES = ("complete", "quadratic")
GRAPH = {"max_degree": 2, "min_points": 6, "points_per_coefficient": 2}
PAIRED_FIELDS = ("case", "archive", "offer", "source", "ledger")
ARCHIVES = {
    "complete": ("sparse-consensus-summary.json.gz", "b843cfad5e324ad0c856019e3e607634a526f422520cc89e163bc3da6d58df73"),
    "quadratic": ("paid-quadratic.json.gz", "9237e3c1d1cbcca9b234dcb5782c1667857efe201683d84634e732004d2e40e1"),
    "installed": ("track-quadrature.json.gz", "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"),
}


def sealed(mode):
    name, pin = ARCHIVES[mode]
    raw = (HERE / "measurements" / name).read_bytes()
    if sha256(raw).hexdigest() != pin:
        raise ValueError(f"Archived {mode} control changed")
    table = json.loads(gzip.decompress(raw))
    return table["runs"] if mode == "installed" else table


def check_binding(identity, archived, mode):
    if any(identity.get(k) != archived[k] for k in (*PAIRED_FIELDS, "native_sha256")):
        raise ValueError(f"Original {mode} packet, authority, archive or offer changed")
    if mode == "quadratic" and (
        identity["graph_parameters"] != archived["graph_parameters"]
        or identity["selection"]["mask_sha256"] != archived["selection"]["mask_sha256"]
    ):
        raise ValueError("Paid visit mask or quadratic graph changed")


def check_installed_binding(identity, installed):
    if (identity["source"]["raw_authority"] != installed["raw_authority"]
            or any(identity[k] != installed[k] for k in ("case", "archive", "offer"))):
        raise ValueError("Installed comparator uses a different recording, causal archive or offer")


def prepare(case, mode):
    from leo.contracts.digests import canonical_digest

    native, rows, _, clocks, archive, offer, identity = bound_inputs(case)
    controls = sealed(mode)
    if mode == "quadratic":
        native, _, stats = prepare_paid(native, rows, clocks, identity, "margin")
        identity.update(selection=stats, graph_parameters=GRAPH)
    identity.update(mode=mode, native_sha256=canonical_digest(native))
    check_binding(identity, controls[case][mode]["identity"], mode)
    return native, archive, offer, identity


def run(case, mode, output, *, preparation_audit=None):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected the shared Gauss slot with one numerical thread")
    publication, spec = configuration()
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core
    from blind_joint_route import make_route
    from certified_salvage import propose
    from lighter_joint_estimator import update

    native, archive, offer, identity = prepare(case, mode)
    stock_solve, bare_prepare, factory = (algo08_position.solve, algo08_position.prepare_native_scan,
                                         algo08_position.TrackConfig)
    attempts, fallback, preparation, owners = [], [], [], {}

    def observed(document, reader, assets, supplied):
        active_prepare = algo08_position.prepare_native_scan
        stock_prepare = bare_prepare if preparation_audit == "original-instrumentation" else active_prepare

        def prepare_native(*args, **kwargs):
            start_cpu, start_wall = process_time(), perf_counter()
            prepared = stock_prepare(*args, **kwargs)
            graph = prepared["tracks"]
            preparation.append(dict(status=prepared["status"], observations=len(graph["observations"]),
                                    arcs=len(graph["tracks"]), graph_points=graph["graph_points"],
                                    curved=len(graph["curved_indices"]), cpu_s=process_time()-start_cpu,
                                    elapsed_s=perf_counter()-start_wall))
            return prepared

        def inspect_only(prepared, *_args, **_kwargs):
            preparation[-1]["prepared_sha256"] = prepared_digest(prepared)
            return dict(status="withheld", reason="preparation_audit_only", arms={arm: {"latlon": None} for arm in ARMS})

        full = make_route(v5_core.infer, reader, fallback, repair=True, signed_finish=True)
        candidate = make_route(full, reader, attempts, repair=True, signed_finish=True,
                               joint_proposal=partial(propose, certified=True), signed_updater=update)
        config = (lambda **cfg: quadratic(factory(**cfg))) if mode == "quadratic" else factory
        with (patch.object(v5_core, "infer", inspect_only if preparation_audit else candidate),
              patch.object(algo08_position, "prepare_native_scan", prepare_native),
              patch.object(algo08_position, "TrackConfig", config)):
            decision, packet, policy = stock_solve(document, reader, assets, supplied)
        if packet is not None:
            if not packet["position_grid"]["complete"]:
                raise ValueError("Returned fit lacks complete numerical evidence")
            owners.update({arm: [[r["observation_id"], r["norad"], r["role"], r["measured_cfo_hz"]]
                                 for r in packet["rows"][arm]] for arm in ARMS})
        return decision, packet, policy

    start_cpu, start_wall = process_time(), perf_counter()
    try:
        with patch.object(algo08_position, "solve", observed):
            result = solve(publication, spec, native, archive, offer)
    except ValueError as exc:
        if str(exc) != "cavity nomination failed: ValueError('nonempty observation mask matching full design required')":
            raise
        result = dict(status="failed", reason=str(exc), arms={}, cpu_s=process_time()-start_cpu,
                      elapsed_s=perf_counter()-start_wall, clock_scope="saved solve including raised exception")
    if archive_identity(archive) != identity["archive"]:
        raise ValueError("Causal archive changed during the trial")
    if len(fallback) != sum(a.get("decision") == "fallback" for a in attempts):
        raise ValueError("Expected telemetry for each original signed fallback")
    result.pop("owner_rows", None)
    names = ("paid_certified_trial.py", "paid-certified-protocol.md", "paid_graph_trial.py", "paid_quadratic.py",
             "certified_salvage.py", "lighter_joint_estimator.py", "family_pool_closure.py", "blind_joint_route.py")
    result.update(identity=identity, host=host, attempts=attempts, fallback=fallback, prepared=preparation,
                  selected_rows=owners, sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in names})
    if preparation_audit:
        if attempts or fallback or result["reason"] != "preparation_audit_only":
            raise ValueError("The preparation audit unexpectedly ran inference")
        result["preparation_audit"] = preparation_audit
    write(output, result)


def prepared_digest(prepared):
    from leo.contracts.digests import canonical_digest

    if prepared["status"] != "inputs_prepared":
        return canonical_digest(prepared)
    sky = prepared["sky"]
    bank = {key: (str(value.dtype), list(value.shape), sha256(value.tobytes(order="C")).hexdigest())
            for key, value in sky["bank"].items()}
    return canonical_digest(dict(prepared, sky=dict(sky, bank=bank)))


def matched_owners(complete, paid):
    """Compare physical observations and separate a changed receiver CFO from a label change."""
    result = {}
    for arm in ARMS:
        full = {oid: (norad, role, cfo) for oid, norad, role, cfo in complete.get(arm, [])}
        small = {oid: (norad, role, cfo) for oid, norad, role, cfo in paid.get(arm, [])}
        shared = full.keys() & small.keys()
        same = {oid for oid in shared if full[oid][2] == small[oid][2]}
        result[arm] = dict(shared_visits=len(shared), shared_same_cfo=len(same),
                           reassigned_same_cfo=sum(full[k][0] != small[k][0] for k in same),
                           role_changes_same_cfo=sum(full[k][1] != small[k][1] for k in same),
                           lost=len(full.keys() - small.keys()), new=len(small.keys() - full.keys()))
    return result


def projected_cpu(complete, paid, solve_cpu):
    return (complete["ledger"]["acquisition_cpu_s"] - complete["replay"]["all_native_cpu_s"]
            + paid["paid_native_cpu_s"] + paid["selection_cpu_s"] + solve_cpu)


def actual_exterior(row):
    return row["status"] == "withheld" and row["reason"] == "both_receivers_support_far_exterior"


def score(directory, summary, full):
    from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
    from mixture_score import section

    paths = {case: {mode: directory / f"{case}-{mode}.json" for mode in MODES} for case in CASES}
    runs = {case: {mode: read(path) for mode, path in modes.items()} for case, modes in paths.items()}
    archived = {mode: sealed(mode) for mode in (*MODES, "installed")}
    for case, rows in runs.items():
        for mode, row in rows.items():
            identity = row["identity"]
            check_binding(identity, archived[mode][case][mode]["identity"], mode)
            if any(identity[k] != rows["complete"]["identity"][k] for k in PAIRED_FIELDS):
                raise ValueError("Complete and paid packet do not share the original recording offer")
            if case.startswith("south-"):
                check_installed_binding(identity, archived["installed"][case]["stock"]["identity"])
                if identity["native_sha256"] != runs["south-containing"][mode]["identity"]["native_sha256"]:
                    raise ValueError("Southern offers differ in receiver packet")

    truth = references()
    physical, = [r for r in read(PHYSICAL)["cases"] if r["dataset_label"] == CASES[0] and r["authority_eligible"]]
    truth[CASES[0]] = [physical["reference"][k] for k in ("latitude_deg", "longitude_deg")]
    results = {}
    for case, rows in runs.items():
        old = archived["complete"][case]["complete"]
        small = archived["quadratic"][case]["quadratic"]
        stock = archived["installed"].get(case, {}).get("stock")
        containing = face_clearance_km(old["identity"]["offer"], truth[case]) >= 0
        outcomes = dict(containing=containing, complete_old_signed=old["charged"],
                        quadratic_old_signed=small["charged"], installed_cpu_s=None if stock is None else stock["cpu_s"],
                        owners_paid_vs_complete=matched_owners(rows["complete"]["selected_rows"],
                                                              rows["quadratic"]["selected_rows"]))
        for mode, row in rows.items():
            fit = section(row["arms"], truth[case], old["result"]["arms"])
            screen = (row["status"] == "ok" and all(a["delta_error_km"] is not None and a["delta_error_km"] <= .25
                      for a in fit["arms"].values())) if containing else actual_exterior(row)
            source = old if mode == "complete" else small
            outcomes[mode] = dict(
                **{k: row.get(k) for k in ("cpu_s", "elapsed_s", "status", "reason", "orbit_policy", "associated", "grid_points")},
                screen=screen, graph=row["prepared"], exact_vs_same_packet_old_signed={key: row.get(key) == source["result"].get(key)
                    for key in ("arms", "owners", "science", "status", "reason", "grid_points")
                    if key in row or key in source["result"]},
                versus_complete_old_signed=fit,
                versus_same_packet_old_signed=section(row["arms"], truth[case], source["result"]["arms"]),
                versus_installed=None if stock is None else section(row["arms"], truth[case], stock["arms"]),
                versus_complete_certified=section(row["arms"], truth[case], rows["complete"]["arms"]),
                projected_acquisition_and_solve_cpu_s=(old["identity"]["ledger"]["acquisition_cpu_s"] + row["cpu_s"]
                    if mode == "complete" else projected_cpu(old["identity"], row["identity"]["selection"], row["cpu_s"])),
                attempt=[dict(route=a.get("decision"), reason=a.get("reason"), signed=a.get("signed", {}).get("status"),
                              signed_reason=a.get("signed", {}).get("reason"),
                              warm_accepted=a.get("warm_signed_fit", {}).get("accepted"),
                              closure_rounds=len(a.get("pool_closure", {}).get("rounds", [])),
                              closure_admissions=[cycle["admitted_norads"] for cycle in a.get("pool_closure", {}).get("rounds", [])],
                              salvage=a.get("certified_salvage"), exterior=a.get("exterior"),
                              clocks={k: v for k, v in a.items() if k.endswith("_clocks")}) for a in row["attempts"]],
                fallback=[dict(route=a.get("decision"), reason=a.get("reason"), signed=a.get("signed", {}).get("status"),
                               exterior=a.get("exterior")) for a in row["fallback"]])
        results[case] = outcomes
    verification = dict(archives={name: digest for name, digest in ARCHIVES.values()},
                        inputs={path.name: sha256(path.read_bytes()).hexdigest() for modes in paths.values() for path in modes.values()},
                        references={path.name: sha256(path.read_bytes()).hexdigest() for path in (PHYSICAL, SIMULATED)})
    write(summary, dict(cases=results, verification=verification))
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(runs=runs, scores=results, verification=verification),
                                             separators=(",", ":"), allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("case", choices=CASES)
    runner.add_argument("mode", choices=MODES)
    runner.add_argument("output", type=Path)
    runner.add_argument("--preparation-audit", choices=("original-instrumentation", "released"))
    scorer = commands.add_parser("score")
    for name in ("directory", "summary", "full"):
        scorer.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
