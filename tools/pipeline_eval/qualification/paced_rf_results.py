"""Authenticate live oldest-RF emissions, fit their actual packets, and compare measured FIFO."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km
from ..variants import rf_waiting
from . import adaptive_arrival_position as position
from . import arrival_queue as pace
from . import bracketed_position, paced_original_results, screening_figures
from . import paced_rf as trial
from .arrival_queue_results import observed, terminal
from .bracketed_position_results import service_result
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHOD = "paced_oldest_rf"
FIFO = paced_original_results.METHOD[trial.paced_original.ORIGINAL]
RAW = "raw-prediction-lock.json"
PREDICTIONS = "prediction-lock.json"
POSITIONS = "positions.jsonl.gz"
BINDINGS = ("paired_capture_sha256", "original_request_sha256", "catalog_sha256", "tile")
PARENT = trial.paced_original.source.ORIGINAL
REPORT = trial.REPORT


def readlines(path):
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def original():
    lock = sealed(PARENT, PREDICTIONS, trial.paced_original.source.CAPTURE_SEAL)
    doc = pace.readgz(whole_iq.checked(PARENT / "native.json.gz", lock["files"]["native.json.gz"]))
    source = whole_iq.read(
        whole_iq.checked(PARENT / "source-lock.json", lock["files"]["source-lock.json"])
    )
    return doc, source


def account(rows, admissions, expected):
    """Check chronological retirement, actual prior starts, and all RF admission transitions."""
    if [r["visit"] for r in rows] != list(range(len(expected))):
        raise ValueError("Detector did not retire all physical arrivals in order")
    if [r["visit"] for r in admissions] != list(range(len(expected))):
        raise ValueError("Admission trace did not cover every original arrival")
    starts = {r["started_ns"]: r for r in rows if r["outcome"] == "emitted"}
    actions = Counter()
    expected_retirement = {}
    end, retired = -1, -1
    for row, ledger, due in zip(rows, admissions, expected, strict=True):
        visit = row["visit"]
        if any(row[k] != v for k, v in due.items()) or row["retired_ns"] < retired:
            raise ValueError("Recorded packet changed provenance or physical retirement order")
        retired = row["retired_ns"]
        action = ledger["action"]
        actions[action] += 1
        if due["status"] == "invalid_capture":
            if row["outcome"] != action or set(ledger) != {"visit", "action"}:
                raise ValueError("A hardware-invalid arrival changed a waiting slot")
        else:
            if ledger["rf_key"] != row["rf_key"] or row["rf_key"][1] != due["center_hz"]:
                raise ValueError("Actual admission lost its independently authenticated RF key")
            expected_retirement[visit] = "emitted"
        if action in ("replaced_waiter", "rejected"):
            old = ledger["compared_waiter"]
            if old >= visit or admissions[old]["action"] not in ("waiting", "replaced_waiter"):
                raise ValueError("Replacement targeted a nonwaiting arrival")
            previous, incoming = tuple(rows[old]["rf_key"]), tuple(row["rf_key"])
            snapshot = {}
            for key, stamp in zip((previous, incoming), ledger["last_starts_ns"], strict=True):
                if stamp is None:
                    continue
                started = starts.get(stamp)
                if started is None or tuple(started["rf_key"]) != key or started["visit"] >= visit:
                    raise ValueError("RF age included an unstarted visit or a future arrival")
                snapshot[key] = stamp
            if rf_waiting.replace_waiter(trial.MODE, previous, incoming, snapshot) != (
                action == "replaced_waiter"
            ):
                raise ValueError("Measured transition differs from the frozen RF rule")
            if action == "replaced_waiter":
                expected_retirement[old] = "replaced"
                if rows[old].get("replaced_by") != visit:
                    raise ValueError("Displaced visit is missing its actual replacement")
            else:
                expected_retirement[visit] = "rejected"
        if row["outcome"] in ("emitted", "invalid_capture"):
            packet = row["packet"]
            if pace.fingerprint(packet) != due["full_visit_sha256"]:
                raise ValueError("Actual original native packet changed on reauthentication")
            if row["outcome"] == "emitted":
                if row["started_ns"] < end:
                    raise ValueError("More than one original detector worker overlapped")
                end = row["emitted_ns"]
        elif "packet" in row or "started_ns" in row:
            raise ValueError("A discarded observation entered the original detector")
    actual = {
        r["visit"]: r.get("queue_reason", r["outcome"])
        for r in rows
        if r["outcome"] != "invalid_capture"
    }
    if expected_retirement != actual:
        raise ValueError("Queued, displaced, rejected and emitted conservation failed")
    return dict(actions)


def material(document, emitted, probes, route):
    retained = set(emitted)
    if probes != [p for p in document["source"]["probes"] if p["visit_index"] in retained]:
        raise ValueError("Fresh actual probes differ from the selected original reference")
    identity = whole_iq.recording.digest(["oldest-rf-paced-retained/v1", route, emitted, probes])
    return dict(
        document,
        source=dict(document["source"], probes=probes, analysis_manifest_sha256=identity),
        provenance=dict(
            document["provenance"],
            processed_windows=len(emitted),
            run_id="replay-" + identity[7:39],
            scope="Actual oldest-RF emissions",
        ),
    )


def measure(work, out):
    if (out / PREDICTIONS).exists():
        raise FileExistsError("Live receiver predictions are already sealed")
    plan = whole_iq.read(out / "source-lock.json")
    for file, digest in plan["programs"].items():
        whole_iq.checked(Path(file), digest)
    worker = work / trial.CASE / trial.MODE
    expected = pace.readgz(
        whole_iq.checked(
            out / "events.json.gz", plan["cases"][trial.CASE]["modes"][trial.MODE]["sha256"]
        )
    )
    rows, witness, service, complete = terminal(worker, expected)
    raw = out / "raw"
    files = ["source-lock.json", "events.json.gz", "PROTOCOL.md"]
    ready = whole_iq.checked(
        trial.paced_original.REPORT / "ready.json", plan["cases"][trial.CASE]["ready_sha256"]
    )
    write(raw / "staged-source.json", ready.read_bytes())
    files.append("raw/staged-source.json")
    for name in ("plan.json", "service.json", "service.log", "service-launch.json", "end.json"):
        if (worker / name).is_file():
            write(raw / name, (worker / name).read_bytes())
            files.append(f"raw/{name}")
    admissions = readlines(worker / "admission.jsonl")
    if complete:
        whole_iq.checked(worker / "admission.jsonl", witness["admission_sha256"])
        if not witness["exact_iq_manifest"] or witness["end"]["cpus"] != [trial.CPU]:
            raise ValueError("Live receiver left its bound staged waveform or CPU")
        actions = account(readlines(worker / "visits.jsonl"), admissions, expected)
    else:
        actions = {}
    for name, data in (("trace.json.gz", rows), ("admission.json.gz", admissions)):
        pace.writegz(raw / name, data)
        files.append(f"raw/{name}")
    packets = {row["visit"]: row["packet"] for row in rows if row["outcome"] == "emitted"}
    visits, probes, support = paced_original_results.retained(rows, packets)
    summary = observed(rows, witness, trial.CASE, trial.MODE, complete, expected)
    summary.update(
        support,
        actions=actions,
        all_retained_exact=complete,
        systemd_wall_s=service.get("service_wall_s"),
        external_staged_iq_bytes=whole_iq.read(ready)["bytes"],
    )
    save_json(out / "timing.json", summary)
    files.append("timing.json")
    save_json(out / RAW, dict(cases=[trial.CASE], files={n: _sha(out / n) for n in files}))
    raw_receipt = [RAW]
    case, request = whole_iq.binding(trial.CASE)
    doc, capture = original()
    job = dict(
        id=trial.CASE,
        method=METHOD,
        native_sha256=None,
        emitted_visits=visits,
        tile=case["regions"][0],
        catalog_sha256=case["catalog"]["sha256"],
        original_request_sha256=case["request"]["sha256"],
        paired_capture_sha256=case["native"]["sha256"],
        boundary="Original timed I/Q through actual oldest-RF emissions",
        **support,
    )
    if complete and visits:
        release_path = trial.paced_original.source.SCREEN / "latency-and-support/fifth-completion"
        release_seal = sealed(release_path, "prediction-lock.json")
        release = whole_iq.read(
            whole_iq.checked(
                release_path / "source-lock.json", release_seal["files"]["source-lock.json"]
            )
        )
        bracketed_position.check_release(release)
        if (
            release["receiver_files"] != capture["receiver_files"]
            or case != plan["cases"][trial.CASE]["capture"]["case"]
        ):
            raise ValueError("Compact solver or causal physical request changed")
        folder = work / trial.CASE / "position"
        folder.mkdir(exist_ok=False)
        payload = material(doc, visits, probes, witness["output_sha256"])
        native_sha, request_sha = position.position_input(
            folder, case, request, release, payload, trial.CPU
        )
        job.update(native_sha256=native_sha, request_sha256=request_sha)
        write(out / "native.json.gz", gzip.compress((folder / "native.json").read_bytes(), mtime=0))
        save_json(
            out / "position-input-lock.json",
            dict(job=job, native_sha256=native_sha, request_sha256=request_sha),
        )
        whole_iq.checked(folder / "native.json", native_sha)
        whole_iq.checked(folder / "request.json", request_sha)
        bracketed_position.launch_case(folder, trial.CPU)
        job["result"], job["position_resources"] = service_result(folder, trial.CPU)
        raw_receipt.extend(("native.json.gz", "position-input-lock.json"))
        for name in ("service.log", "service.json", "start.json", "end.json", "position.json"):
            if (folder / name).is_file():
                write(out / "position" / name, (folder / name).read_bytes())
                raw_receipt.append(f"position/{name}")
    else:
        state = "withheld" if complete else "unavailable"
        job["result"] = position.empty_result(state, "No complete actual receiver factor set")
    pack(out / POSITIONS, [job])
    raw_receipt.append(POSITIONS)
    save_json(
        out / PREDICTIONS, dict(cases=[trial.CASE], files={n: _sha(out / n) for n in raw_receipt})
    )


def compile_rf(doc, fair, fifo):
    valid = {}
    for p in doc["source"]["probes"]:
        key = (p["channel"], int(p["actual_rf_hz"]))
        if key[1] != p["actual_rf_hz"] or valid.setdefault(p["visit_index"], key) != key:
            raise ValueError("Original physical lanes disagree on the exact RF key")
    offered = Counter(valid.values())
    selected = [Counter(valid[i] for i in r["emitted_visits"]) for r in (fifo, fair)]
    return [
        dict(
            channel=key[0],
            actual_rf_hz=key[1],
            valid=offered[key],
            fifo=selected[0][key],
            oldest_rf=selected[1][key],
        )
        for key in sorted(offered)
    ]


def geo_rows(positions, reference):
    geography, rf = [], []
    for item in positions:
        result = item["result"]
        for arm in ARMS:
            value = result.get("arms", {}).get(arm, {})
            geography.append(
                dict(
                    method=item["method"],
                    arm=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=distance_km(value.get("latlon"), reference["truth"]),
                )
            )
            rf.append(
                dict(
                    method=item["method"],
                    arm=arm,
                    rf_rms_hz=value.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(arm + "_frequency_score"),
                )
            )
    for role in ROLES:
        for arm in ARMS:
            value = reference["reference"][role][arm]
            geography.append(
                dict(
                    method=f"capture-era-v5/{role}",
                    arm=arm,
                    status=value["status"],
                    reason=value.get("reason"),
                    error_km=value.get("error_km"),
                )
            )
            rf.append(
                dict(
                    method=f"capture-era-v5/{role}",
                    arm=arm,
                    rf_rms_hz=value.get("rf_rms_hz"),
                    frequency_score=None,
                )
            )
    return geography, rf


def plot(out, by_rf, timing):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(11, 4.7), layout="constrained")
    FigureCanvasAgg(fig)
    support, queue = fig.subplots(1, 2)
    for i, (key, label, color) in enumerate(
        (
            ("fifo", "Original FIFO", "#516879"),
            ("oldest_rf", "Least recently started RF", "#207858"),
        )
    ):
        support.bar(
            [j + 0.34 * i for j in range(len(by_rf))],
            [r[key] for r in by_rf],
            width=0.32,
            label=label,
            color=color,
        )
    support.set(
        xticks=[i + 0.17 for i in range(len(by_rf))],
        xticklabels=[r["channel"] for r in by_rf],
        xlabel="Physical channel",
        ylabel="Visits emitted",
        title="Measured RF support on DS29-0082",
    )
    support.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.21), frameon=False, ncols=2, fontsize=8
    )
    labels = ["Original FIFO · CPU10", "Oldest RF · CPU12"]
    offsets = [0, 0]
    for key, label, color in (
        ("native_packets_emitted", "Emitted", "#207858"),
        ("queue_drops", "Queue drop", "#aeb7bd"),
        ("invalid_capture", "Hardware invalid", "#494b58"),
    ):
        counts = [r[key] for r in timing]
        queue.barh(labels, counts, left=offsets, color=color, label=label)
        offsets = [x + y for x, y in zip(offsets, counts, strict=True)]
    queue.set(xlabel="Physical visits", title="All 6,772 scheduled arrivals")
    queue.invert_yaxis()
    queue.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.21), frameon=False, ncols=3, fontsize=8
    )
    for ax, direction in ((support, "y"), (queue, "x")):
        ax.set_axisbelow(True)
        ax.grid(axis=direction, alpha=0.24)
    for suffix in ("png", "pdf"):
        fig.savefig(out / f"stage.{suffix}", dpi=155)


def publish(out):
    current = sealed(out, PREDICTIONS)
    (fair,) = rows_from(whole_iq.checked(out / POSITIONS, current["files"][POSITIONS]))
    previous = trial.paced_original.REPORT
    stock_seal = sealed(previous, PREDICTIONS)
    stocks = rows_from(whole_iq.checked(previous / POSITIONS, stock_seal["files"][POSITIONS]))
    (fifo,) = [r for r in stocks if r["method"] == FIFO and r["id"] == trial.CASE]
    if any(fair[k] != fifo[k] for k in ("id", *BINDINGS)):
        raise ValueError("Actual fair and FIFO inferences used different causal queries")
    fifo_trace = "raw/original/trace.json.gz"
    a = pace.readgz(whole_iq.checked(previous / fifo_trace, stock_seal["files"][fifo_trace]))
    fair_audit = sealed(out, RAW)
    fair_trace = "raw/trace.json.gz"
    b = pace.readgz(whole_iq.checked(out / fair_trace, fair_audit["files"][fair_trace]))
    # Bind each FIFO emission to independently measured physical route and authority.
    for r, s in zip(a, b, strict=True):
        if any(r[k] != s[k] for k in (*trial.paced_original.CLOCK, "full_visit_sha256")):
            raise ValueError("FIFO and oldest-RF used different original IQ or arrival clocks")
    doc, _ = original()
    rf = compile_rf(doc, fair, fifo)
    _, refs = held_references(None, (trial.CASE,))
    geography, fit = geo_rows((fair, fifo), refs[0])
    older_file = "raw/original/witness.json"
    fifo_witness = whole_iq.read(
        whole_iq.checked(previous / older_file, stock_seal["files"][older_file])
    )
    scheduled = pace.readgz(out / "events.json.gz")
    control = observed(a, fifo_witness, trial.CASE, "fifo", fifo["raw_verified"], scheduled)
    result = whole_iq.read(out / "timing.json")
    keys = (
        "mode",
        "native_packets_emitted",
        "queue_drops",
        "invalid_capture",
        "detector_cpu_s",
        "service_cpu_s",
        "service_wall_s",
        "memory_peak_bytes",
        "rss_peak_kib",
        "age_p50_ms",
        "age_p95_ms",
        "native_wall_p50_ms",
        "native_wall_p95_ms",
        "prefetch_late",
    )
    timing = [
        {k: row[k] for k in keys}
        | dict(
            retained_positive_probes=item.get("positive_probes"),
            retained_positive_visits=item.get("positive_visits"),
            position_wall_s=item.get("position_resources", {}).get("wall_s"),
            position_cpu_s=item.get("position_resources", {}).get("cpu_s"),
            replacements=row.get("actions", {}).get("replaced_waiter"),
            arrival_to_emission_within_20ms=item.get("emissions_with_age_20ms"),
            raw_status=item.get("raw_verified", result["all_retained_exact"]),
        )
        for row, item in ((control, fifo), (result, fair))
    ]
    pack(out / "chart-positions.jsonl.gz", [fair, fifo])
    for name, table in (
        ("geographic", geography),
        ("frequency-fit", fit),
        ("rf-support", rf),
        ("resources", timing),
    ):
        csv_file(out / f"{name}.csv", table)
    combined = [
        dict(row, **{f"{t['mode']}_{k}": t[k] for t in timing for k in keys[1:4]}) for row in rf
    ]
    csv_file(out / "stage.csv", combined)
    plot(out, rf, timing)
    spec = dict(
        version=1,
        id="oldest-rf-live-queue",
        title="Least recently started RF at the recorded pace",
        sample="DS29-0082 actual original-detector runs, 6,772 scheduled visits",
        boundary="One active worker, one waiting visit, full original dual GLRT per emission",
        note="Original FIFO CPU10 and RF replacement CPU12 share the authenticated staged clock.",
        seal="figure-lock.json",
        image="stage.png",
        pdf="stage.pdf",
        csv="stage.csv",
    )
    save_json(out / "stage-figure.json", spec)
    csv_assets = ("rf-support.csv", "resources.csv", "geographic.csv", "frequency-fit.csv")
    chart = dict(
        id="paced-rf-position",
        method=METHOD,
        scope="roof",
        cases="sealed",
        title="Actual oldest-RF and FIFO emissions through compact position",
        caption="DS29-0082 at its recorded pace with one worker and one waiting window. "
        "Inputs consist of authenticated physical emissions.",
        seal="figure-lock.json",
        provenance=list(csv_assets),
        series=[
            dict(
                key=key,
                file="chart-positions.jsonl.gz",
                value=name,
                label=label,
                native_field=BINDINGS[0],
                match=list(BINDINGS),
            )
            for key, name, label in (
                ("one", METHOD, "Least recently started RF"),
                ("stock", FIFO, "Actual original-detector FIFO"),
            )
        ],
    )
    save_json(out / "figures.json", dict(version=2, charts=[chart]))
    assets = (
        *csv_assets,
        "stage-figure.json",
        "stage.pdf",
        "stage.png",
        "stage.csv",
        "figures.json",
        "chart-positions.jsonl.gz",
        PREDICTIONS,
        RAW,
    )
    save_json(
        out / "figure-lock.json",
        dict(
            cases=[trial.CASE],
            files={n: _sha(out / n) for n in assets},
            fifo_prediction_sha256=_sha(previous / PREDICTIONS),
            publisher_sha256=_sha(Path(__file__)),
        ),
    )
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("measure", "publish"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=REPORT)
    args = parser.parse_args()
    if args.action == "measure":
        measure(args.work, args.out)
    else:
        publish(args.out)
