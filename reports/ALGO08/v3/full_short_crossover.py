"""Isolate DS30-0016 detector and solver effects after the genuine raw pair seals."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

from aperture_trial import ARMS, BENCH, archive_identity, configuration, machine, read, write
from mixture_trial import elapsed, summarize


HERE = Path(__file__).resolve().parent
CASE = "DS30-0016"
PAIR = Path("/var/tmp/leo-full-short-DS30-0016-raw")
GATE = Path("/var/tmp/leo-full-short-DS30-0016-far-gate.json")
ARCHIVE = Path("/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0016/tle")
ARCHIVE_DIGEST = "sha256:25bf630b8588a27a23f90de971041ce95b249ce5e1fd2f72144aa8b73945fafc"
RAW_AUTHORITY = "sha256:64e945e9717c2612fdb3118d7b65c713076a1b56f5de49f8fdf291a3220fc252"
REGION = BENCH / "integration02/ds30-station-offer.json"
REGION_PIN = "2698d6858da0a2d989d8c2185c9e3bbbba20d539988204c1f93a591eb9471236"
RECIPE = "13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"
CELLS = {"candidate-stock": ("candidate", "stock"), "stock-candidate": ("stock", "candidate")}
ROWS = ("observation_id", "norad", "role")
GRAPH = {"max_degree": 2, "points_per_coefficient": 2, "min_points": 6}


def digest(raw):
    return sha256(raw).hexdigest()


def check_gate(path):
    value = read(path)
    if value["passed"] is not True:
        raise ValueError("Physical preflight did not pass; no saved crossover is authorized")
    proof, = value["proof"]
    result = proof["result"]
    if (result.get("complete") is not True or result.get("would_withhold") is not True
            or set(result["receivers"]) != {"1", "2"}
            or not all(row.get("unique_exterior") is True for row in result["receivers"].values())
            or value["result"]["status"] != "withheld"
            or value["result"]["attempts"] or value["result"]["ranks"]):
        raise ValueError("Physical preflight lacks the genuine original early exterior proof")
    return digest(path.read_bytes())


def normalized_owners(native, rows):
    """Bind published owner ids to their original physical receiver, epoch and CFO."""
    if rows is None:
        return None
    source = native["source"]
    observed = {}
    for probe in source["probes"]:
        candidates = [row for row in probe["candidates"] if row["passed_fractional_margin_gate"] is True]
        if not candidates:
            continue
        strongest = max(candidates, key=lambda row: (row["fractional_margin"], -row["candidate_rank"]))
        rx, counter = probe["receiver_id"], probe["valid_start_counter"]
        visit = (rx, probe["channel"], probe["actual_rf_hz"], probe["edge"], counter)
        oid = "sha256:" + digest(f"{source['session_id']}:{rx}:{counter}".encode())
        if oid in observed:
            raise ValueError("Duplicate native physical observation")
        observed[oid] = (visit, strongest["fractional_tracking_cfo_hz"], strongest["integer_epoch_sample"],
                         strongest["fractional_epoch_offset_samples"])
    return {arm: [dict(zip(ROWS, row, strict=True), measurement=observed[row[0]]) for row in arm_rows]
            for arm, arm_rows in rows.items()}


def compare_owners(first, second):
    if first is None or second is None:
        return None
    changes = {}
    for arm in ARMS:
        a, b = ({tuple(row["measurement"][0]): row for row in owners.get(arm, [])} for owners in (first, second))
        shared = a.keys() & b.keys()
        same = {k for k in shared if a[k]["measurement"][1] == b[k]["measurement"][1]}
        same_factor = {k for k in same if a[k]["measurement"][2:] == b[k]["measurement"][2:]}
        changes[arm] = dict(shared_sample_counter=len(shared), same_counter_cfo=len(same), same_fractional_factor=len(same_factor),
                            shared_counter_changed_cfo=len(shared - same), lost=len(a.keys() - b.keys()), new=len(b.keys() - a.keys()),
                            norad_changed_same_cfo=sum(a[k]["norad"] != b[k]["norad"] for k in same),
                            role_changed_same_cfo=sum(a[k]["role"] != b[k]["role"] for k in same))
    return changes


def diagonal(folder, label, region, *, stock_detector):
    from leo.contracts.digests import canonical_digest
    from leo.presentation.localization_v3 import owner_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    sealed = folder / "joint-research-receipt.json"
    research = read(sealed)
    receipt = research["receipt"]
    stock = label == "stock"
    if (research["stock_control"] != stock or bool(research.get("optimized_full_catalogue")) == stock
            or research["saved_digest"] is not None or research["saved_handoff_manifest"] is not None):
        raise ValueError("Expected the requested fresh authenticated raw diagonal")
    root = folder / "fast-scan-automatic-work"
    native_path, = root.glob("*/detections.json")
    native = read(native_path)
    terminal = read(root / receipt["run_id"] / "terminal.json")
    source, provenance = native["source"], native["provenance"]
    standard = FastStandardAnalysisStore(folder)
    detail = standard.detail(receipt["run_id"])
    if (canonical_digest(native) != terminal["native_sha256"] or canonical_digest(terminal) != receipt["terminal_sha256"]
            or detail["terminal_sha256"] != receipt["terminal_sha256"] or detail["input_sha256"] != terminal["native_sha256"]
            or terminal["region"] != region or receipt["region"] != region or detail["region"] != region
            or source["session_id"] != receipt["session_id"] or terminal["session_id"] != receipt["session_id"]
            or detail["raw_authority"] != RAW_AUTHORITY or source["raw_recording_authority_digest"] != RAW_AUTHORITY
            or provenance["window_count"] != 808 or provenance["processed_windows"] != 713
            or len(source["probes"]) != 1426 or detail["state"] != receipt["decision"]):
        raise ValueError(f"The {label} raw diagonal failed the native/terminal/recording binding")
    audit = read(folder / "receiver-audit.json")
    pin = stock_detector if stock else RECIPE
    analysis = canonical_digest(["cancellation", RAW_AUTHORITY, pin, source["probes"]])
    if (provenance["detector_sha256"] != "sha256:" + pin or audit["detector_pin"] != pin
            or analysis != source["analysis_manifest_sha256"] or analysis != audit["analysis_manifest"]
            or audit["input_manifest"] != source["input_manifest_sha256"] or audit["recording_authority"] != RAW_AUTHORITY
            or sum(audit["native"]["native_calls"].values()) != 1426 or audit["issued"] != 808
            or audit["graph"] != ("installed" if stock else GRAPH)):
        raise ValueError(f"The {label} raw detector and graph provenance changed")
    if not stock and (canonical_digest(audit["recipe"]) != "sha256:" + RECIPE or len(research["early_regional"]) != 1):
        raise ValueError("Expected the genuine frozen candidate and its original pre-inference region proof")
    for name, value in research["source_sha256"].items():
        if name == "joint_publication.py" or name.startswith("installed/"):
            continue
        if digest((HERE / name).read_bytes()) != value:
            raise ValueError(f"Crossover solver source differs from sealed diagonal: {name}")
    rows = research.get("selected_rows")
    complete = receipt["decision"] == "complete"
    owners = {arm: row["owner_sha256"] for arm, row in detail.get("arms", {}).items()} if complete else {}
    associated = {arm: row["associated_points"] for arm, row in detail["arms"].items()} if complete else {}
    if complete and rows is not None:
        for arm in ARMS:
            chosen = {oid: norad for oid, norad, _role in rows[arm]}
            if len(chosen) != associated[arm] or owner_digest(chosen) != owners[arm]:
                raise ValueError("Saved final owners must reproduce the official diagonal owner digest")
    if complete:
        grid = standard.position_grid(receipt["run_id"])
        path = standard.position_path(receipt["run_id"])
        if (research["solve"]["grid_complete"] is not True or not grid["complete"]
                or canonical_digest(grid) != research["evidence"]["grid"]
                or canonical_digest(path) != research["evidence"]["path"]):
            raise ValueError("Raw diagonal has incomplete or changed numerical evidence")
    elif receipt["decision"] != "withheld" or rows or detail["artifacts"]:
        raise ValueError("Raw diagonal has incomplete science or withholding evidence")
    result = dict(status=terminal["decision"], reason=terminal["reason"], arms=terminal["arms"], owners=owners,
                  associated=associated, selected_rows=normalized_owners(native, rows if complete else {}),
                  native_sha256=terminal["native_sha256"], manifest_sha256=source["input_manifest_sha256"],
                  session=source["session_id"], detector_sha256=provenance["detector_sha256"],
                  detector_recipe=audit["recipe"], raw_authority=RAW_AUTHORITY,
                  input=research["input"], solve=research["solve"], route=research["route"],
                  route_details=research.get("route_details"), early_regional=research.get("early_regional"),
                  source_sha256=research["source_sha256"],
                  raw_receipt_sha256=digest(sealed.read_bytes()))
    return native, result


def load_pair(pair, gate, stock_detector):
    from leo.contracts.algo08_region import Algo08Region

    authorized = check_gate(gate)
    raw_request = pair / "request.json"
    request = read(raw_request)
    region_bytes = REGION.read_bytes()
    region = Algo08Region.parse(json.loads(region_bytes)).document()
    archive = archive_identity(ARCHIVE)
    if (digest(region_bytes) != REGION_PIN or request["offered_region"] != region or request["raw_authority"] != RAW_AUTHORITY
            or request["gate_sha256"] != authorized or archive != request["archive"]
            or archive["snapshots_sha256"] != ARCHIVE_DIGEST):
        raise ValueError("Raw-pair request differs from the frozen physical input and offer")
    natives, sealed = {}, {}
    for role in ("stock", "candidate"):
        process = read(pair / f"{role}-process.json")
        if process["exit_code"] != 0:
            raise ValueError("Both real physical arms must exit successfully before a crossover")
        natives[role], sealed[role] = diagonal(pair / role, role, region, stock_detector=stock_detector)
        if sealed[role]["manifest_sha256"] != request["inventory_sha256"] or sealed[role]["session"] != request["session"]:
            raise ValueError("Both authentic native inputs must bind the same raw inventory")
    if natives["stock"]["clock_anchor"] != natives["candidate"]["clock_anchor"] or \
            natives["stock"]["delivery_clocks"] != natives["candidate"]["delivery_clocks"]:
        raise ValueError("Matched physical counters must share one capture clock")
    return natives, sealed, dict(region=region, archive=archive, gate_sha256=authorized, request_sha256=digest(raw_request.read_bytes()))


def run(cell, output, *, pair, gate):
    host = machine()
    if (host["cpu"] != [2] or host["nice"] < 15 or "prio 7" not in host["ionice"]
            or any(n != "1" for n in host["threads"].values())):
        raise ValueError("Expected one shared low-priority Gauss slot")
    release, spec = configuration()
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position, algo08_scan
    from tools.pipeline_eval.variants import v5_core
    from early_region import before_fit
    from joint_publication import full_catalogue_route
    from optimized_grid import reduced_grid
    from paid_quadratic import quadratic
    from prepared_exterior import handoff

    natives, sealed, provenance = load_pair(pair, gate, spec["detector_sha256"])
    detector, algorithm = CELLS[cell]
    attempt, regional, graph = [], [], []

    def analyze(recording, _root, assets, archive, offered):
        from tools.pipeline_eval.variants.experimental import regional_bound_guard

        if recording.exists() or archive != ARCHIVE or offered.document() != provenance["region"]:
            raise ValueError("Only the sealed detector packet and original physical offer are permitted")
        reader = TleArchiveReader(archive)
        installed = v5_core.infer
        start = process_time(), perf_counter()
        prepared = None
        grid = None
        with ExitStack() as scope:
            if algorithm == "candidate":
                route = full_catalogue_route(installed, reader, attempt, optimized=True)
                live, prepared, _ = scope.enter_context(handoff(reader))
                grid = scope.enter_context(reduced_grid())
                route = before_fit(route, reader, regional_bound_guard.causal_probes, regional, live.match)
                from_config = algo08_position.TrackConfig
                scope.enter_context(patch.object(algo08_position, "TrackConfig", lambda **values: quadratic(from_config(**values))))
            else:
                route = installed

            def observe(document, *args, **kwargs):
                tracks = document["tracks"]
                graph.append(dict(status=document["status"], graph_points=tracks["graph_points"], tracks=len(tracks["tracks"]),
                                  curved=len(tracks["curved_indices"])))
                return route(document, *args, **kwargs)

            scope.enter_context(patch.object(v5_core, "infer", observe))
            decision, packet, policy = algo08_position.solve(natives[detector], reader, assets, offered)
        clock = elapsed(*start)
        if not graph or (decision["status"] == "ok") != (packet is not None):
            raise ValueError("Expected a single saved crossover solve and a genuine paired outcome")
        result, _ = summarize(decision, packet, policy)
        rows = {} if packet is None else {arm: [[r[k] for k in ROWS] for r in packet["rows"][arm]] for arm in ARMS}
        if packet is not None and not packet["position_grid"]["complete"]:
            raise ValueError("Saved crossover fix lacks its original complete numerical evidence")
        result.update(solve=clock, selected_rows=normalized_owners(natives[detector], rows), attempts=attempt,
                      early_regional=regional, graph=graph, prepared_exterior=prepared, reduced_grid=grid,
                      detector_source_sha256=sealed[detector]["native_sha256"], detector_identity=sealed[detector]["detector_sha256"],
                      detector_recipe=sealed[detector]["detector_recipe"], solver=algorithm)
        return result

    with TemporaryDirectory() as scratch, patch.object(algo08_scan, "analyze", analyze):
        root = Path(scratch)
        args = SimpleNamespace(recording=root / "unused-recording", bulk_root=root, archive=ARCHIVE, region=REGION)
        result = release.run(args, spec)
    if archive_identity(ARCHIVE) != provenance["archive"]:
        raise ValueError("Physical archive changed during the crossover")
    result.update(provenance=provenance, raw_diagonals=sealed, cell=cell, host=host,
                  driver_sha256=digest(Path(__file__).read_bytes()),
                  protocol_sha256=digest((HERE / "full-short-crossover-protocol.md").read_bytes()))
    write(output, result)


def score(directory, summary, full):
    from aperture_score import PHYSICAL
    from mixture_score import section
    from tools.pipeline_eval.scoring import distance_km

    sources = {label: directory / f"{label}.json" for label in CELLS}
    crossed = {label: read(path) for label, path in sources.items()}
    first, second = crossed.values()
    if first["raw_diagonals"] != second["raw_diagonals"] or first["provenance"] != second["provenance"]:
        raise ValueError("The crossover cells do not bind the same genuine raw pair")
    for label, row in crossed.items():
        data, fit = CELLS[label]
        if (row["cell"] != label or row["solver"] != fit
                or row["detector_source_sha256"] != row["raw_diagonals"][data]["native_sha256"]):
            raise ValueError("Saved crossover route or detector changed")
    controls = first["raw_diagonals"]
    rows = dict(crossed, **{"stock-stock": controls["stock"], "candidate-candidate": controls["candidate"]})
    anchor, = [row["reference"] for row in read(PHYSICAL)["cases"] if row["dataset_label"] == CASE and row["authority_eligible"]]
    truth = (anchor["latitude_deg"], anchor["longitude_deg"])
    outcomes = {label: dict(status=row["status"], reason=row["reason"], associated=row.get("associated"),
                            solve=row["solve"], fit=section(row["arms"], truth, rows["stock-stock"]["arms"]),
                            grid_points=row["solve"].get("grid_points", row.get("grid_points")),
                            route=row.get("route", row.get("attempts")), early_regional=row.get("early_regional"),
                            graph=row.get("graph", row["solve"].get("preparation"))) for label, row in rows.items()}
    transitions = {label: values for label, values in (
        ("detector_with_stock_solver", ("stock-stock", "candidate-stock")),
        ("detector_with_candidate_solver", ("stock-candidate", "candidate-candidate")),
        ("solver_with_stock_detector", ("stock-stock", "stock-candidate")),
        ("solver_with_candidate_detector", ("candidate-stock", "candidate-candidate")),
    )}
    contrasts = {}
    for label, pair in transitions.items():
        old, new = (rows[key] for key in pair)
        shifts = {}
        for arm in ARMS:
            x, y = (row["arms"][arm].get("latlon") for row in (old, new))
            shifts[arm] = None if x is None or y is None else distance_km(x, y)
        contrasts[label] = dict(before=pair[0], after=pair[1], endpoint_shift_km=shifts,
                                owner_changes=compare_owners(old["selected_rows"], new["selected_rows"]),
                                signed_deltas=section(new["arms"], truth, old["arms"]))
    receipt_pins = {label: digest(path.read_bytes()) for label, path in sources.items()}
    scored = dict(cells=outcomes, contrasts=contrasts, paired_input=first["provenance"],
                  verification=dict(saved=receipt_pins, reference_sha256=digest(PHYSICAL.read_bytes())))
    write(summary, scored)
    with full.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(dict(scores=scored, cells=rows), separators=(",", ":"),
                                             allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    trial = actions.add_parser("run")
    trial.add_argument("cell", choices=CELLS)
    trial.add_argument("output", type=Path)
    trial.add_argument("--pair", type=Path, default=PAIR)
    trial.add_argument("--gate", type=Path, default=GATE)
    scoring = actions.add_parser("score")
    for name in ("directory", "summary", "full"):
        scoring.add_argument(name, type=Path)
    args = vars(parser.parse_args())
    (run if args.pop("action") == "run" else score)(**args)
