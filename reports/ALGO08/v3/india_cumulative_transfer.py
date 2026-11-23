"""Compare the newer cumulative numerical route and named v3 on public saved India."""

import argparse
import gzip
import json
from contextlib import ExitStack
from functools import partial
from math import isclose
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, FROZEN, configuration, machine, read, write
from india_saved_transfer import (
    CASE,
    HISTORY,
    MODES,
    NATIVE_SHA,
    STAGED,
    TREE,
    bind,
    digest,
)

HERE = Path(__file__).resolve().parent
BASE = "00b32f587"
ROUTES = ("stock", "cumulative")
ORDER = [("matched-tile", "stock"), ("matched-tile", "cumulative"),
         ("omitted-tile", "cumulative"), ("omitted-tile", "stock")]
PRIOR = HERE / "measurements/india-regional-diagnostic.json.gz"
PRIOR_SHA = "3879605a5b35d2bbb9e714cb9bd5ce1f40cb28d43ec6443ff6772879e3641913"
LIBRARIES = {
    "geographic": (
        "/dev/shm/leo-v3-saved-0316-pair-01/geographic_library.so",
        "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee",
    ),
    "regional": (
        "/dev/shm/leo-v3-saved-0316-pair-01/regional_track_library.so",
        "5e96851c0f9c479dbb176eeb3f2ba143c461d590a9b35b00fb5c1d7ce984d098",
    ),
    "frontier": (
        "/dev/shm/leo-v3-saved-0316-pair-01/frontier_block_library.so",
        "adfbfca33caee3c6b337ddf401db1112e525867e451ad010eb30cb65965ce042",
    ),
    "grid": (
        "/dev/shm/leo-cumulative-grid-projection-01/projection.so",
        "7ac9f74eb08d1992bde8738dbc8f6ec9687eb7fe4f5d5f4ae3301ddfa061d0fb",
    ),
}


def checked(path, expected):
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"Archived file or pinned library changed: {path}")
    return data


def verify_authority(recording, root, archive, offer, args, identity):
    if (
        recording != args.recording or recording.exists() or root != args.output
        or archive != args.archive or offer.document() != identity["offer"]
    ):
        raise ValueError("Expected only the saved waveform packet and its original offer")


def signed_stock_match(archived, current):
    keys = ("identity", "status", "reason", "orbit_policy", "arms", "owners", "associated",
            "science", "objective_replay", "grid_points", "selected_rows")
    if differences := [key for key in keys if archived.get(key) != current.get(key)]:
        raise ValueError(f"Installed v3 differs from its verified India replay: {differences}")


def denied(*_args, **_kwargs):
    raise ValueError("Raw input is outside the saved-only experiment")


def run(mode, route, output):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Use the shared low-priority Gauss slot with one numerical thread")
    publication, spec = configuration()
    import joint_publication
    from exact_graph_execution import graph_execution
    from exact_phase_forecast import active_forecast
    from full_short_run import geographic_projection
    from grid_feature_projection import active_projection
    from mixture_trial import summarize
    from regional_probe_block_binding import guarded_projection

    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_scan

    native, archive, region, identity, verify = bind(STAGED, mode)
    prior = json.loads(gzip.decompress(checked(PRIOR, PRIOR_SHA)))["runs"]
    cumulative = route == "cumulative"
    paths = {name: Path(path) for name, (path, _) in LIBRARIES.items()} if cumulative else {}
    for name, path in paths.items():
        checked(path, LIBRARIES[name][1])
    audit = dict(graph={}, grid={}, forecast={})
    result = {}
    args = SimpleNamespace(
        recording=output.parent / "raw-input-is-absent", archive=archive, region=region, output=output,
        saved=None, saved_digest=None, verify_images=False, stock_control=not cumulative,
        optimized_full_catalogue=cumulative, skip_empty_proof=True,
    )

    def numerical_only(recording, root, assets, archive, offer):
        verify_authority(recording, root, archive, offer, args, identity)
        if result:
            raise ValueError("Expected a single numerical handoff")
        with ExitStack() as stack:
            if cumulative:
                stack.enter_context(graph_execution(enabled=True, audit=audit["graph"]))
                stack.enter_context(active_projection(paths["grid"], audit["grid"]))
            decision, packet, policy = algo08_scan.solve(native, TleArchiveReader(archive), assets, offer)
        if decision["status"] not in ("ok", "withheld") or (decision["status"] == "ok") != (packet is not None):
            raise ValueError("Expected a complete numerical decision")
        evidence, _ = summarize(decision, packet, policy)
        result.update(evidence)
        if packet is not None:
            grid = packet["position_grid"]
            if (not grid["complete"] or not grid["matched_c_grid"] or set(packet["arms"]) != set(ARMS)
                    or any(abs(v) > 1e-5 for v in packet["objective_replay"].values())):
                raise ValueError("A fix needs a complete paired grid and objective replay")
            result["selected_rows"] = {
                arm: [[r["observation_id"], r["norad"], r["role"]] for r in packet["rows"][arm]]
                for arm in ARMS
            }
        result["regional_guard"] = decision.get("metrics", {}).get("regional_bound_guard")
        return {"decision": "complete" if packet is not None else "withheld"}

    projection = None
    forecast = None
    if cumulative:
        projection = partial(guarded_projection, paths["geographic"], paths["regional"],
                             paths["frontier"], geographic_projection)
        forecast = partial(active_forecast, audit["forecast"])
    with (
        patch.object(joint_publication, "configuration", return_value=(publication, spec)),
        patch.object(algo08_scan, "analyze", numerical_only),
    ):
        run_details = joint_publication.run(
            args, detector_override=denied, detector_description="locked public India detector",
            early_regional=cumulative, geographic_projector=projection, reuse_cold_rows=cumulative,
            reuse_grid_phase_states=cumulative, phase_forecast=forecast,
        )
    verify()
    if not result or canonical_digest(native) != identity["native_canonical_sha256"]:
        raise ValueError("The post-detector solve did not consume the unchanged native document")
    result.update(
        identity=identity, mode=mode, route=route, solver="sha256:" + FROZEN, candidate_base=BASE,
        worker_digest=digest(Path(__file__).read_bytes()), prior_sha256=PRIOR_SHA, host=host,
        solve=run_details["solve"], source_sha256=run_details["source_sha256"], exact_options=audit,
        early_regional=run_details.get("early_regional"), solver_route=run_details["route"],
        route_details=run_details["route_details"], recovery=run_details.get("recovered_inference"),
        library_sha256={name: LIBRARIES[name][1] for name in paths},
    )
    if route == "stock":
        signed_stock_match(prior[mode]["stock"], result)
    write(output / "numerical.json", result)


def score_rows(runs, prior, truth):
    from prospective_0316_solver import owner_delta

    from tools.pipeline_eval.qualification.score_paired_holdout import face_clearance_km
    from tools.pipeline_eval.scoring import distance_km

    results = {}
    for mode, pair in runs.items():
        stock, cumulative = (pair[route] for route in ROUTES)
        for route, row in pair.items():
            if (row["identity"] != stock["identity"] or row["mode"] != mode or row["route"] != route
                    or row["solver"] != "sha256:" + FROZEN or row["candidate_base"] != BASE
                    or row["identity"]["document_sha256"] != NATIVE_SHA):
                raise ValueError("Both methods must bind the same original packet, archive and offer")
        signed_stock_match(prior[mode]["stock"], stock)
        clearance = face_clearance_km(stock["identity"]["offer"], truth)
        expected = 3.5764712370156406 if mode == "matched-tile" else -1.5
        if not isclose(clearance, expected, rel_tol=0, abs_tol=1e-8):
            raise ValueError("The offer is not the previously published geographic test")
        scores = {}
        for name, row in pair.items():
            scores[name] = dict(
                status=row["status"], reason=row["reason"], correct=(row["status"] == "ok") == (clearance >= 0),
                arms={arm: dict(value, error_km=distance_km(value["latlon"], truth))
                      for arm, value in row["arms"].items()},
            )
        stock_rows, cumulative_rows = stock.get("selected_rows", {}), cumulative.get("selected_rows", {})
        results[mode] = dict(
            truth_clearance_km=clearance, scores=scores,
            owners={arm: owner_delta(stock_rows.get(arm, ()), cumulative_rows.get(arm, ()))
                    for arm in ARMS},
            earlier_bare_full_catalogue=prior[mode]["full-catalogue"]["arms"],
        )
    return results


def score(directory, output, summary):
    transfer = run_path(str(HISTORY / "covariance_transfer_trial.py"))
    public = transfer["public"]
    scores = public("truth-after-lock.json.gz", TREE)
    if digest(scores) != json.loads(public("score-lock.json", TREE))["files"]["truth-after-lock.json.gz"]:
        raise ValueError("Published India scoring authority changed")
    truth = json.loads(gzip.decompress(scores))["scene"]["coordinate"]
    paths = {(mode, route): directory / f"{mode}-{route}" / "numerical.json" for mode, route in ORDER}
    runs = {mode: {route: read(paths[mode, route]) for route in ROUTES} for mode in MODES}
    prior = json.loads(gzip.decompress(checked(PRIOR, PRIOR_SHA)))["runs"]
    cases = score_rows(runs, prior, truth)
    result = dict(
        case=CASE, base=BASE, execution_order=ORDER, truth=truth, cases=cases,
        native_sha256=NATIVE_SHA, prior_sha256=PRIOR_SHA, references_sha256=digest(scores),
        pre_score_sha256={f"{mode}-{route}": digest(path.read_bytes())
                          for (mode, route), path in paths.items()},
    )
    write(summary, result)
    with output.open("xb") as stream:
        document = json.dumps(dict(result, runs=runs), separators=(",", ":"), allow_nan=False)
        stream.write(gzip.compress(document.encode(), mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("run")
    worker.add_argument("mode", choices=MODES)
    worker.add_argument("route", choices=ROUTES)
    worker.add_argument("output", type=Path)
    scoring = commands.add_parser("score")
    scoring.add_argument("directory", type=Path)
    scoring.add_argument("output", type=Path)
    scoring.add_argument("summary", type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("command") == "run" else score)(**args)


if __name__ == "__main__":
    main()
