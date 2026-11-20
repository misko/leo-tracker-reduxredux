"""Bind native sample identity and qualify the common fixed-orbit estimator."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from leo.contracts.digests import canonical_digest

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import validate_result
from ..variants import fixed_orbit_position as fit
from . import identity_native_export as adapter
from . import independent_arcs_trial as independent
from .armijo_finish_results import pack
from .cold_input import load
from .cold_missing import _sandbox
from .full_v5_check import BULK, _load_case
from .owner_factor_archive import COMPONENT, _matched_arms
from .prefix_figures import TIMING_IDS

OUT = ROOT / "reports/2026_11_19_receiver_screening/next/identity-ablation"
METHOD = "identity_ablation"
CELLS = ("independent_full", "v5_full", "shared_independent", "shared_v5")
DIAGNOSTIC = ("DS26-0197", "DS29-0316")
CPUS = (14, 15)
CAP = 100
prior = independent.prior
digest = prior.digest
read = prior.read
NATIVE_WORKER = """
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from types import SimpleNamespace

start, cpu = perf_counter(), process_time()
from tools.pipeline_eval.qualification.identity_native_export import export

q = json.load(sys.stdin)
data = q['capture']
capture = SimpleNamespace(**dict(data, catalog=data['catalog'].encode()))
out, training, held = export(capture, q['offer'])
json.dump(dict(result=out, train=training, held=held, wall_s=perf_counter()-start,
               cpu_s=process_time()-cpu, rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),
          sys.stdout, allow_nan=False)
"""
FIT_WORKER = """
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time

from tools.pipeline_eval.variants import fixed_orbit_position as fit

q = json.load(sys.stdin)
sky = q['catalogue']
catalog = fit.Catalogue(**(sky | {'text': sky['text'].encode()}))
rows = {name: [fit.Factor(*r) for r in values] for name, values in q['cells'].items()}
labels = {r.norad for cell in rows.values() for r in cell}
_, bank = fit.orbit_table(catalog, labels, q['offer']['center'])
pair = [i for i, (a,b) in enumerate(zip(rows['shared_independent'], rows['shared_v5'], strict=True))
        if a.norad in bank and b.norad in bank]
for name in ('shared_independent', 'shared_v5'):
    rows[name] = [rows[name][i] for i in pair]
answers = {}
for name, observations in rows.items():
    start, cpu = perf_counter(), process_time()
    result, residuals = fit.solve(observations, catalog, q['offer'])
    answers[name] = dict(result=result, residuals=residuals, wall_s=perf_counter()-start,
                         cpu_s=process_time()-cpu, rss_kib=getrusage(RUSAGE_SELF).ru_maxrss)
json.dump(dict(cells=answers, shared_indices=pair), sys.stdout, allow_nan=False)
"""


def jobs():
    auth = prior.archive.REPORT
    prior.archive.base.secant_full._verify_files(auth, read(auth / "prediction-lock.json")["files"])
    prior.archive.base.secant_full._verify_files(
        independent.OUTPUT, read(independent.OUTPUT / "prediction-lock.json")["files"]
    )
    old = {q["recording"] for q in read(independent.OUTPUT / "blind-plan.json")["cases"]}
    exact = {r["id"]: r for r in read(auth / "plan.json")["cases"] if r["cohort"] == "roof"}
    reserve = []
    for prefix in ("DS26-", "DS29-"):
        candidates = [k for k in exact if k.startswith(prefix) and k not in old | set(TIMING_IDS)]
        reserve += sorted(
            candidates, key=lambda k: digest(("identity-ablation-20261119/" + k).encode())
        )[:2]
    if len(reserve) != 4:
        raise ValueError("the prespecified reserve is incomplete")
    return [
        dict(
            id=case,
            cohort="diagnostic" if case in DIAGNOSTIC else "reserve",
            packet=exact[case]["packet"],
        )
        for case in (*DIAGNOSTIC, *reserve)
    ]


def v5_rows(authority, probes, original_reference):
    request = BULK / authority["request"]["path"]
    raw = request.read_bytes()
    spec = json.loads(raw)
    receipt_path = request.parent.parent / "baseline-execution.json"
    raw_receipt = receipt_path.read_bytes()
    cert = json.loads(raw_receipt)
    worker = cert["worker"]
    if (
        digest(raw) != authority["request"]["sha256"]
        or spec["job"]["native_input"]["sha256"] != "sha256:" + authority["native"]["sha256"]
        or cert["status"] != "complete"
        or cert["role"] != "baseline"
        or cert["request_sha256"] != worker["request_sha256"]
        or cert["request_sha256"] != canonical_digest(spec)
        or cert["request_sha256"] != original_reference["request_sha256"]
        or digest(raw_receipt) != original_reference["execution_sha256"]
    ):
        raise ValueError("v5 owner receipt does not authenticate the exact capture and release")
    stable, unequal_arms = _matched_arms(worker)
    rows = []
    for key, r in stable.items():
        probe = probes[key]
        match = COMPONENT.fullmatch(r["component"])
        if (
            not match
            or (int(match[1]), int(match[2]), float(match[3]))
            != (r["receiver"], r["channel"], probe["actual_rf_hz"])
            or (r["receiver"] - 1, r["channel"], r["time_s"])
            != (probe["receiver_id"], probe["channel"], probe["time_s"])
        ):
            raise ValueError("published identity differs from native receiver, RF, or sample time")
        gated = [p for p in probe["candidates"] if p["passed_fractional_margin_gate"]]
        c = max(gated, key=lambda p: (p["fractional_margin"], -p["candidate_rank"]))
        if abs(fit.fold(c["fractional_tracking_cfo_hz"] - r["measured_cfo_hz"])) > 1e-6:
            raise ValueError("v5 CFO does not reproduce the native gated winner")
        rows.append(adapter.physical_row(probe, c, r["norad"]) | dict(upstream_role=r["role"]))
    return rows, dict(
        execution_sha256=digest(raw_receipt),
        request_sha256=digest(raw),
        owner_sha256={a: worker["arms"][a]["owner_sha256"] for a in fit.ARMS},
        total_publication_rows=len(stable) + unequal_arms,
        excluded_arm_unstable=unequal_arms,
        retained_publication_rows=len(rows),
        original_used_catalogue_in_history=authority["catalog"]["sha256"]
        in spec["causal_snapshots"].values(),
    )


def stratify(native, original):
    def physical(rows):
        result = {(r["observation_id"], r["candidate_rank"]): r for r in rows}
        if len(result) != len(rows):
            raise ValueError("a physical GLRT peak received multiple factors")
        return result

    a, b = physical(native), physical(original)
    intersection = sorted(a.keys() & b.keys())
    for key in intersection:
        if any(
            a[key][name] != b[key][name]
            for name in (
                "receiver",
                "channel",
                "rf_hz",
                "time_s",
                "measured_cfo_hz",
                "epoch_sample",
                "counter",
            )
        ):
            raise ValueError("shared observation identifier has inconsistent actual measurements")
    native_slots, original_slots = {k for k, _ in a}, {k for k, _ in b}
    if len(native_slots) != len(a) or len(original_slots) != len(b):
        raise ValueError("one arm has two peaks from a single native receiver opportunity")
    return dict(
        independent_full=native,
        v5_full=original,
        shared_independent=[dict(a[k]) for k in intersection],
        shared_v5=[dict(b[k]) for k in intersection],
    ), dict(
        exact_shared_rows=len(intersection),
        shared_opportunities_different_rank=len(native_slots & original_slots) - len(intersection),
        agreeing_labels=sum(a[k]["norad"] == b[k]["norad"] for k in intersection),
        disagreeing_labels=sum(a[k]["norad"] != b[k]["norad"] for k in intersection),
    )


def _call(argv, payload):
    p = subprocess.run(argv, input=encoded(payload), capture_output=True, timeout=CAP)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors="replace")[-2600:])
    return json.loads(p.stdout)


def _mount(argv, files):
    for p in files:
        argv[-4:-4] = ["--ro-bind", str(p), str(Path("/worker") / p.relative_to(ROOT))]
    return argv


def _narrow(r):
    return [
        r["time_s"],
        r["rf_hz"],
        r["measured_cfo_hz"],
        r["norad"],
        2 * r["receiver"] + int(r["channel"] > 4),
    ]


def run_case(q, cpu, maps, work):
    case = q["id"]
    start = perf_counter()
    capture = load(case)
    packet = q["packet"]
    if (
        capture.native_sha256,
        capture.catalog_sha256,
        capture.cutoff_utc_ns,
        capture.catalog_timestamp_ns,
    ) != (
        packet["native"]["sha256"],
        packet["catalogue"]["sha256"],
        packet["cutoff"],
        packet["catalog_timestamp"],
    ):
        raise ValueError("native clock and catalogue differ from sealed original request")
    offer = packet["offer"]
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = NATIVE_WORKER
    _mount(
        argv,
        [
            Path(adapter.__file__),
            Path(independent.solver.__file__),
            Path(independent.previous.paired.__file__),
        ],
    )
    trace = _call(
        argv, dict(capture=vars(capture) | {"catalog": capture.catalog.decode()}, offer=offer)
    )
    trace["archive_to_export_s"] = perf_counter() - start
    if case in maps["independent"]:
        saved = maps["independent"][case]["result"]
        if any(trace["result"][k] != saved[k] for k in ("arms", "status", "reason")):
            raise ValueError("traced export changed the frozen anonymous receiver output")
    auth = _load_case(case)
    idx, indexed = adapter.physical_index(capture, auth["session_id"])
    native, ties = adapter.bind_independent(trace["train"] + trace["held"], idx)
    read_original = perf_counter()
    original, v5_receipt = v5_rows(auth, indexed, maps["original"][case]["baseline"])
    v5_receipt["export_wall_s"] = perf_counter() - read_original
    cells, overlap = stratify(native, original)
    overlap.update(
        independent_full_rows=len(native),
        v5_full_rows=len(original),
        native_duplicate_cfo_resolved_by_trace=ties,
    )
    fit_source = Path(fit.__file__)
    narrow = {name: list(map(_narrow, rows)) for name, rows in cells.items()}
    argv = _sandbox(cpu, [fit_source])
    argv[argv.index("/worker/solver.py")] = str(Path("/worker") / fit_source.relative_to(ROOT))
    argv[-1] = FIT_WORKER
    _mount(argv, [ROOT / "tools/pipeline_eval/reference/grid.py"])
    sky = dict(
        text=capture.catalog.decode(),
        anchor_utc_ns=capture.anchor_utc_ns,
        cutoff_utc_ns=capture.cutoff_utc_ns,
        collected_utc_ns=capture.catalog_timestamp_ns,
        duration_s=capture.duration_s,
    )
    started = perf_counter()
    result = _call(["nice", "-n", "10", *argv], dict(catalogue=sky, offer=offer, cells=narrow))
    fit_wall = perf_counter() - started
    for name in CELLS[2:]:
        cells[name] = [cells[name][j] for j in result["shared_indices"]]
    published = []
    for name, cell in result["cells"].items():
        residuals = cell.pop("residuals")
        validate_result(cell["result"])
        factors = cells[name]
        for arm, observed in residuals.items():
            if observed and len(observed) != len(factors):
                raise ValueError("residual array no longer matches physical factors")
            for r, residual in zip(factors, observed, strict=False):
                r.setdefault("residuals", {})[arm] = residual
        published.append(
            dict(
                id=case,
                cohort=q["cohort"],
                method=METHOD,
                cell=name,
                tile=offer,
                input_sha256=digest(encoded(packet)),
                native_sha256=capture.native_sha256,
                catalog_sha256=capture.catalog_sha256,
                factor_sha256=digest(encoded(list(map(_narrow, factors)))),
                privileged=name in ("v5_full", "shared_v5"),
                **cell,
            )
        )
    report = dict(
        id=case,
        overlaps=overlap,
        v5_receipt=v5_receipt,
        upstream=dict(
            train_points=len(trace["train"]),
            held_points=len(trace["held"]),
            wall_s=trace["wall_s"],
            archive_to_export_s=trace["archive_to_export_s"],
            cpu_s=trace["cpu_s"],
            rss_kib=trace["rss_kib"],
            arms=trace["result"]["arms"],
            status=trace["result"]["status"],
        ),
        standalone_sandbox_batch_wall_s=fit_wall,
        held_phase_origin="frozen independent c0 or all original stable labelled factors",
        retained_causal_shared=len(result["shared_indices"]),
    )
    save_json(work / (case + ".json"), dict(rows=published, source=report, factors=cells))
    print(case, overlap, [(r["cell"], r["result"]["reason"]) for r in published], flush=True)


def run(work):
    work.mkdir(parents=True, exist_ok=False)
    queries = jobs()
    source = [
        Path(__file__),
        Path(adapter.__file__),
        Path(fit.__file__),
        Path(independent.solver.__file__),
        Path(independent.previous.paired.__file__),
        *prior.sources()["peak_paths"][0],
        Path(load.__code__.co_filename),
        Path(prior.__file__),
        Path(_matched_arms.__code__.co_filename),
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        OUT / "PROTOCOL.md",
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source}

    source_lock = hashes()
    original = prior.archive.base.secant_full.REPORT
    prior.archive.base.secant_full._verify_files(original, read(original / "receipt.json")["files"])
    refs = read(original / "original-v5-inputs.json")
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            source=source_lock,
            cpus=list(CPUS),
            cap_s=CAP,
            v5_receipt_sha256=digest((original / "receipt.json").read_bytes()),
            v5_bindings={q["id"]: refs[q["id"]]["baseline"] for q in queries},
        ),
    )
    maps = dict(
        original=refs, independent=read_predictions(independent.OUTPUT / "positions.jsonl.gz")
    )
    start = perf_counter()

    def lane(i):
        for q in queries[i :: len(CPUS)]:
            run_case(q, CPUS[i], maps, work)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    if source_lock != hashes():
        raise ValueError("frozen source closure changed during the matched run")
    detail = [read(work / (q["id"] + ".json")) for q in queries]
    files = {
        name: pack(OUT, name, content)
        for name, content in (
            ("positions.jsonl.gz", [r for row in detail for r in row["rows"]]),
            (
                "factor-ledger.jsonl.gz",
                [
                    dict(id=q["id"], cells=row["factors"])
                    for q, row in zip(queries, detail, strict=True)
                ],
            ),
        )
    }
    save_json(OUT / "source-audit.json", [r["source"] for r in detail])
    files.update(
        {
            name: digest((OUT / name).read_bytes())
            for name in ("blind-plan.json", "source-audit.json")
        }
    )
    save_json(
        OUT / "prediction-lock.json",
        dict(cases=[q["id"] for q in queries], files=files, batch_wall_s=perf_counter() - start),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--show-roster", action="store_true")
    args = parser.parse_args()
    if args.show_roster:
        print([(q["id"], q["cohort"]) for q in jobs()])
    else:
        run(args.work)
