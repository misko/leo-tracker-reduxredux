"""Model fixed and adaptive FIFO detector policies and fit the locked packet sets."""

import argparse
import csv
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from math import isclose
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.arrival_policy import ArrivalPolicy
from . import adaptive_arrival_position as original
from . import arrival_queue
from . import bracketed_position as solver
from .bracketed_position_results import service_result
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file

REPORT = original.REPORT.with_name("queue-capacity")
SCALES = (4, 6, 8, 9, 10, 12, 16)
FOCUS = 9
POLICIES = ("stock", "fifth", "adaptive")
CPUS = {"DS26-0197": 10, "DS29-0316": 11}
METHOD = {mode: "queue_capacity_" + mode for mode in POLICIES}
POSITIONS = "positions.jsonl.gz"
MODEL = "queue-model.csv"
SELECTIONS = "queue-selections.json.gz"
PLAN = "source-lock.json"
PREDICTIONS = "prediction-lock.json"
ORDER = original.ORDER
PHYSICAL_FIELDS = ("visit", "arrival_ns", "delivery_clock", "sample_start", "sample_end", "status")


def validate_events(events):
    stock, fifth = (events[mode] for mode in POLICIES[:2])
    previous = -1
    for visit, (a, b) in enumerate(zip(stock, fifth, strict=True)):
        if (
            a["visit"] != visit
            or a["arrival_ns"] < previous
            or a["status"] not in ("processed", "invalid_capture")
            or any(a[f] != b[f] for f in PHYSICAL_FIELDS)
        ):
            raise ValueError("the two costs must bind one identical valid physical visit sequence")
        valid = a["status"] == "processed"
        for row in (a, b):
            for field in ("detector_cpu_ns", "detector_wall_ns"):
                cost = row[field]
                if type(cost) is not int or (cost <= 0 if valid else cost != 0):
                    raise ValueError("CPU and wall costs must verify the detector validity status")
        previous = a["arrival_ns"]
    if not stock:
        raise ValueError("expected physical visits")


def replay(events, mode, scale):
    """Return every arrival and the cost-weighted one-worker queue in quarter-ns ticks."""
    policy = ArrivalPolicy(mode)
    finishes = deque()
    trace = []
    for stock, fifth in zip(events["stock"], events["fifth"], strict=True):
        arrival = 4 * stock["arrival_ns"]
        while finishes and finishes[0] <= arrival:
            finishes.popleft()
            policy.finish()
        before = len(finishes)
        row = {k: stock[k] for k in PHYSICAL_FIELDS if k != "delivery_clock"}
        row.update(outstanding_at_admission=before, policy=None, actual_sha256=None)
        if stock["status"] == "invalid_capture":
            row.update(outcome="invalid_capture", actual_sha256=stock["full_visit_sha256"])
        else:
            checked, choice = policy.admit()
            if checked != before:
                raise ValueError("actual admission policy and the FIFO disagree")
            if choice is None:
                row["outcome"] = "queue_drop"
            else:
                source = stock if choice == "stock" else fifth
                begin = finishes[-1] if finishes else arrival
                duration = source["detector_cpu_ns"] * scale
                finishes.append(begin + duration)
                row.update(
                    policy=choice,
                    outcome="emitted",
                    actual_sha256=source["full_visit_sha256"],
                    start_ticks=begin,
                    finish_ticks=finishes[-1],
                    service_ticks=duration,
                )
        trace.append(row)
    return trace


def summarize(ident, mode, scale, events, trace):
    from .arrival_queue_results import timing_ms

    counts = Counter(r["outcome"] for r in trace)
    live = [r for r in trace if r["outcome"] == "emitted"]
    choices = Counter(r["policy"] for r in live)
    last = trace[-1]["arrival_ns"]
    elapsed = max((r["finish_ticks"] for r in live), default=0)
    duration = sum(r["service_ticks"] for r in live)
    return dict(
        id=ident,
        mode=mode,
        cpu_scale=scale / 4,
        physical_slots=len(trace),
        valid_slots=len(trace) - counts["invalid_capture"],
        invalid_capture=counts["invalid_capture"],
        completed=counts["emitted"],
        dropped=counts["queue_drop"],
        stock_calls=choices["stock"],
        fifth_calls=choices["fifth"],
        max_waiting=max((r["outstanding_at_admission"] for r in live), default=0),
        drain_ms=max(0, elapsed / 4 - last) / 1e6,
        delivery_span_s=last / 1e9,
        modeled_detector_service_s=duration / 4e9,
        archived_offered_cpu_s=(
            sum(r["detector_cpu_ns"] for r in events[mode]) / 1e9 if mode != "adaptive" else None
        ),
        **timing_ms((r["start_ticks"] / 4 - r["arrival_ns"] for r in live), "wait"),
        **timing_ms((r["finish_ticks"] / 4 - r["arrival_ns"] for r in live), "age"),
    )


def one_x(previous, historic_drops, row, trace):
    fields = (
        "physical_slots",
        "valid_slots",
        "completed",
        "invalid_capture",
        "dropped",
        "max_waiting",
        "drain_ms",
        "delivery_span_s",
    )
    quantiles = tuple(
        f"{name}_{metric}_ms" for name in ("wait", "age") for metric in ("p50", "p95", "p99", "max")
    )
    current_drops = [r["visit"] for r in trace if r["outcome"] == "queue_drop"]
    if (
        any(
            not isclose(float(previous[k]), row[k], rel_tol=1e-12, abs_tol=1e-12)
            for k in (*fields, *quantiles)
        )
        or not isclose(float(previous["offered_cpu_s"]), row["archived_offered_cpu_s"])
        or current_drops != [r["visit"] for r in historic_drops]
    ):
        raise ValueError(f"1× model failed the historical CPU queue parity for {row['id']}")


def history():
    queue_path = original.QUEUE / "stage-lock.json"
    source_lock = whole_iq.read(original.QUEUE / "source-lock.json")
    stage = whole_iq.read(queue_path)
    if stage["files"]["source-lock.json"] != original.QUEUE_PIN or set(stage["cases"]) != set(CPUS):
        raise ValueError("historical queue seal does not identify the two physical control streams")
    names = ("queue-model.csv", "modeled-drops.json.gz")
    history_paths = {
        name: whole_iq.checked(original.QUEUE / name, stage["files"][name]) for name in names
    }
    for case in source_lock["cases"].values():
        for mode in case["modes"].values():
            if stage["files"][mode["events"]] != mode["sha256"]:
                raise ValueError("event costs disagree with the original queue source lock")
            whole_iq.checked(original.QUEUE / mode["events"], mode["sha256"])

    def matching(row):
        return (
            row["clock"] == "cpu" and int(row["workers"]) == 1 and str(row["waiting_slots"]) == "1"
        )

    with history_paths[names[0]].open() as fp:
        models = {(r["id"], r["mode"]): r for r in csv.DictReader(fp) if matching(r)}
    drops = {
        (r["id"], r["mode"]): r["dropped_visits"]
        for r in arrival_queue.readgz(history_paths[names[1]])
        if matching(r)
    }
    return models, drops, _sha(queue_path)


def exact_or_derived(ident, mode, trace, docs, refs, old_positions):
    retained, selected, drops, counts = original.chosen_packets(trace, mode, docs, refs)
    # Full exact inputs permit reuse; canonical bytes distinguish signed zero.
    choices = (mode,) if mode != "adaptive" else POLICIES[:2]
    probes = encoded(retained)
    for source in choices:
        if not drops and probes == encoded(docs[source]["source"]["probes"]):
            return docs[source], source, counts, selected, drops
    trace_sha = sha256(encoded(trace)).hexdigest()
    lineage = original.recording_to_v5.digest(
        [
            "counterfactual-arrival-queue/v1",
            ident,
            mode,
            trace_sha,
            {key: row["native_sha256"] for key, row in old_positions.items()},
            selected,
        ]
    )
    stock = docs["stock"]
    provenance = dict(
        stock["provenance"],
        run_id="queue-" + lineage[7:39],
        processed_windows=len(selected),
        scope="Counterfactual FIFO-selected archived native packets",
    )
    used = {key for _, key, _ in selected}
    if len(used) == 1:
        provenance["detector_sha256"] = docs[next(iter(used))]["provenance"]["detector_sha256"]
    else:
        provenance.pop("detector_sha256", None)
    doc = dict(
        stock,
        provenance=provenance,
        source=dict(stock["source"], probes=retained, analysis_manifest_sha256=lineage),
    )
    return doc, None, counts, selected, drops


def freeze(work):
    report = REPORT
    if (report / PLAN).exists():
        raise FileExistsError("the queue capacity study is already frozen")
    work.mkdir(parents=True, exist_ok=False)
    previous, previous_drops, historical_stage_sha = history()
    inherited = whole_iq.read(
        whole_iq.checked(original.PARENT / "prediction-lock.json", original.PARENT_PIN)
    )
    parent_resources = whole_iq.read(original.parent_member("resources.json", inherited))
    leases, summaries, selections, reused = {}, [], {}, {}
    receiver = None
    for ident, cpu in CPUS.items():
        docs, refs, old_positions, case, request, release = original.load_control(ident)
        validate_events(refs)
        receiver = release
        for scale in SCALES:
            for mode in POLICIES:
                trace = replay(refs, mode, scale)
                row = summarize(ident, mode, scale, refs, trace)
                summaries.append(row)
                key = f"{ident}/{mode}/{scale}/4"
                selections[key] = dict(
                    dropped=[r["visit"] for r in trace if r["outcome"] == "queue_drop"],
                    fifth=[r["visit"] for r in trace if r["policy"] == "fifth"],
                    trace_sha256=sha256(encoded(trace)).hexdigest(),
                )
                if scale == 4 and mode != "adaptive":
                    authority = ident, original.ARCHIVE[mode]
                    one_x(previous[authority], previous_drops.get(authority, []), row, trace)
                if scale != FOCUS:
                    continue
                doc, reuse, counts, selected, _ = exact_or_derived(
                    ident, mode, trace, docs, refs, old_positions
                )
                selections[key]["selected"] = selected
                if reuse:
                    record = old_positions[reuse]
                    resources = parent_resources[ident][original.ARCHIVE[reuse]]
                    reused[f"{ident}/{mode}"] = dict(
                        result=record["result"],
                        resources=dict(
                            wall_s=resources.get("position_s"),
                            charge_peak_bytes=resources.get("max_bytes"),
                            timing_scope="Archived position stage in the complete whole-IQ service",
                        ),
                    )
                    native, request_sha = record["native_sha256"], None
                else:
                    out = work / ident / mode
                    out.mkdir(parents=True, exist_ok=False)
                    native, request_sha = original.position_input(
                        out, case, request, release, doc, cpu
                    )
                base = old_positions["stock"]
                leases[f"{ident}/{mode}"] = dict(
                    id=ident,
                    method=METHOD[mode],
                    mode="matched-tile",
                    policy=mode,
                    cpu=cpu,
                    tile=base["tile"],
                    catalog_sha256=base["catalog_sha256"],
                    original_request_sha256=base["original_request_sha256"],
                    paired_capture_sha256=base["paired_capture_sha256"],
                    native_sha256=native,
                    request_sha256=request_sha,
                    reuse=reuse,
                    counts=counts,
                    model_scale=FOCUS / 4,
                    selection_sha256=sha256(encoded(selected)).hexdigest(),
                )
    csv_file(report / MODEL, summaries)
    arrival_queue.writegz(report / SELECTIONS, selections)
    save_json(work / "archived-fits.json", reused)
    paths = (
        Path(__file__),
        Path(original.__file__),
        Path(solver.__file__),
        Path(service_result.__code__.co_filename),
        Path(ROOT / "tools/pipeline_eval/variants/arrival_policy.py"),
    )
    lock = dict(
        cases=list(CPUS),
        cpu=CPUS,
        order=ORDER,
        protocol_sha256=_sha(report / "PROTOCOL.md"),
        queue_source_sha256=original.QUEUE_PIN,
        prior_stage_sha256=historical_stage_sha,
        prior_prediction_sha256=original.PARENT_PIN,
        receiver=receiver["receiver"],
        receiver_files=receiver["receiver_files"],
        native_sources=receiver["native_sources"],
        limits=dict(cap_s=solver.LIMIT, memory_max=whole_iq.MEMORY, swap_max=0, nice=10),
        one_x_historical_parity=True,
        trials=leases,
        programs={str(p.relative_to(ROOT)): _sha(p) for p in paths},
        files={name: _sha(report / name) for name in (MODEL, SELECTIONS)},
        archived_fit_sha256=_sha(work / "archived-fits.json"),
    )
    save_json(report / PLAN, lock)
    save_json(work / PLAN, lock)


def run(work):
    report = REPORT
    lock = whole_iq.read(whole_iq.checked(report / PLAN, _sha(work / PLAN)))
    solver.check_release(lock)
    whole_iq.checked(report / "PROTOCOL.md", lock["protocol_sha256"])
    for name, digest in lock["programs"].items():
        whole_iq.checked(ROOT / name, digest)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    reused = whole_iq.read(
        whole_iq.checked(work / "archived-fits.json", lock["archived_fit_sha256"])
    )
    if (report / PREDICTIONS).is_file():
        raise FileExistsError("queue positions already sealed")

    def lane(ident):
        rows = []
        for mode in ORDER[ident]:
            key = f"{ident}/{mode}"
            planned = lock["trials"][key]
            out = work / ident / mode
            if planned["reuse"]:
                measured = reused[key]
            else:
                whole_iq.checked(out / "native.json", planned["native_sha256"])
                whole_iq.checked(out / "request.json", planned["request_sha256"])
                if not (out / "service.json").is_file():
                    solver.launch_case(out, CPUS[ident])
                result, resources = service_result(out, CPUS[ident])
                write(report / f"{ident}-{mode}-service.log", (out / "service.log").read_bytes())
                measured = dict(
                    result=result, resources=dict(resources, timing_scope="Fresh capped factor fit")
                )
            rows.append(dict(planned, **measured))
        return rows

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [row for lane_rows in pool.map(lane, CPUS) for row in lane_rows]
    pack(report / POSITIONS, rows)
    files = [PLAN, MODEL, SELECTIONS, POSITIONS, "PROTOCOL.md"]
    files.extend(p.name for p in sorted(report.glob("*-service.log")))
    save_json(
        report / PREDICTIONS, dict(cases=list(CPUS), files={n: _sha(report / n) for n in files})
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run"))
    parser.add_argument("work", type=local_output)
    args = parser.parse_args()
    (freeze if args.action == "freeze" else run)(args.work)


if __name__ == "__main__":
    main()
