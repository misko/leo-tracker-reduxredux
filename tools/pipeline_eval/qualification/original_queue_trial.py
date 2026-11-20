"""Replay original-detector arrivals into one waiting slot and fit its actual packets."""

import argparse
import csv
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import distribution
from ..variants import capture_bursts, rf_waiting
from . import adaptive_arrival_position as emitted
from . import arrival_queue, bracketed_position, capture_whole, capture_whole_results
from .bracketed_position_results import service_result
from .complete_detector_roster import member
from .fresh_replay_results import sealed
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

PARENT = capture_whole.REPORT
REPORT = PARENT.parents[1] / "original-support/queue-selection"
PARENT_SHA = "84f9aa52911b391a8a23c60a57dd0f3e8d4106060ba94fb7e92b40215c829d33"
CPUS = (12, 13)
LABELS = {
    "fifo": "First waiting visit",
    "latest": "Newest waiting visit",
    "oldest_rf": "Least recently processed RF",
}


def load_inputs():
    parent = sealed(PARENT, "prediction-lock.json", PARENT_SHA)
    release = whole_iq.read(member(PARENT, parent, "source-lock.json"))
    doc = arrival_queue.readgz(member(PARENT, parent, "native.json.gz"))
    with member(PARENT, parent, "timing.csv").open() as stream:
        costs = list(csv.DictReader(stream))
    valid = dict(capture_bursts.inventories(doc))
    lane_rf = {p["channel"]: p["actual_rf_hz"] for p in doc["source"]["probes"]}
    if any(lane_rf[p["channel"]] != p["actual_rf_hz"] for p in doc["source"]["probes"]):
        raise ValueError("the channel index changed its physical RF during the recording")
    arrivals = []
    clocks = doc["delivery_clocks"]
    for visit, (clock, cost) in enumerate(zip(clocks, costs, strict=True)):
        if int(cost["visit"]) != visit or (cost["status"] == "processed") != (visit in valid):
            raise ValueError("measured detector clocks disagree with hardware support")
        arrivals.append(
            (
                clock["monotonic_ns"] - clocks[0]["monotonic_ns"],
                valid.get(visit),
                round(float(cost["cpu_ms"]) * 1e6),
            )
        )
    if whole_iq.receiver_identity(Path(release["receiver"])) != release["receiver_files"]:
        raise ValueError("the installed compact solver differs from the measured control")
    return parent, release, doc, arrivals


def forecast(out, arrivals):
    streams, summary = {}, []
    for workers in (1, 2, 4, 8, 12):
        for policy in rf_waiting.POLICIES:
            events = rf_waiting.simulate(arrivals, workers, policy)
            name = f"{policy}-{workers}"
            streams[name] = events
            lanes = Counter(arrivals[v][1] for v, _, _ in events)
            ages = [(end - arrivals[v][0]) / 1e6 for v, _, end in events]
            dist = distribution(ages)
            summary.append(
                dict(
                    policy=policy,
                    workers=workers,
                    valid=sum(rf is not None for _, rf, _ in arrivals),
                    emitted=len(events),
                    least_sampled_channel_count=min(lanes.values(), default=0),
                    busiest_channel_count=max(lanes.values(), default=0),
                    by_channel=" ".join(f"{k}={lanes[k]}" for k in sorted(lanes)),
                    due_to_output_median_ms=dist["p50"],
                    due_to_output_p95_ms=dist["p95"],
                    within_20ms=sum(v <= 20 for v in ages),
                    last_due_s=arrivals[-1][0] / 1e9,
                    last_finish_s=max(end for _, _, end in events) / 1e9,
                    detector_cpu_s=sum(arrivals[v][2] for v, _, _ in events) / 1e9,
                )
            )
    arrival_queue.writegz(out / "forecasts.json.gz", streams)
    csv_file(out / "timing.csv", summary)
    return streams


def materialize(work, out):
    parent, release, doc, arrivals = load_inputs()
    case, original = whole_iq.binding(capture_whole.IDENT)
    if (
        case["native"] != release["original"]["native"]
        or case["catalog"] != release["original"]["catalog"]
        or case["request"] != release["original"]["request"]
    ):
        raise ValueError("capture-era factor authority or causal position request changed")
    streams = forecast(out, arrivals)
    protocols = out / "PROTOCOL.md"
    save_json(
        out / "forecast-lock.json",
        dict(
            case=case["id"],
            parent_sha256=PARENT_SHA,
            policy_sha256=_sha(Path(rf_waiting.__file__)),
            protocol_sha256=_sha(protocols),
            harness_sha256=_sha(Path(__file__)),
            files={k: _sha(out / k) for k in ("forecasts.json.gz", "timing.csv")},
        ),
    )
    jobs = []
    for cpu, workers in zip(CPUS, (1, 4), strict=True):
        for policy in rf_waiting.POLICIES:
            name = f"{policy}-{workers}"
            folder = work / name
            folder.mkdir()
            selection = [v for v, _, _ in streams[name]]
            kept = set(selection)
            parent_sha = parent["files"]["native.json.gz"]
            identity = whole_iq.recording.digest(["original-queue/v1", name, parent_sha, selection])
            packets = [p for p in doc["source"]["probes"] if p["visit_index"] in kept]
            if len(packets) != len(kept) * 2 or len(kept) != len(selection):
                raise ValueError("a forecast visit lacks its original pair of measured probes")
            material = dict(
                doc,
                source=dict(doc["source"], probes=packets, analysis_manifest_sha256=identity),
                provenance=dict(
                    doc["provenance"],
                    processed_windows=len(kept),
                    run_id="replay-" + identity[7:39],
                    scope="Original factors retained by a measured-service queue forecast",
                ),
            )
            native, request = emitted.position_input(folder, case, original, release, material, cpu)
            jobs.append(
                dict(
                    id=case["id"],
                    method=f"original_queue_{name}",
                    policy=policy,
                    workers=workers,
                    cpu=cpu,
                    mode="matched-tile",
                    cohort="modeled admissions on a complete recording",
                    paired_capture_sha256=case["native"]["sha256"],
                    catalog_sha256=case["catalog"]["sha256"],
                    original_request_sha256=case["request"]["sha256"],
                    tile=release["original"]["tile"],
                    native_sha256=native,
                    request_sha256=request,
                    selected_visits=len(kept),
                )
            )
    save_json(
        out / "inputs.json", dict(forecast_sha256=_sha(out / "forecast-lock.json"), jobs=jobs)
    )
    return jobs, parent


def run(work, out):
    if (out / "forecast-lock.json").exists():
        raise FileExistsError("use a fresh report directory for another numerical experiment")
    work.mkdir(parents=True, exist_ok=False)
    jobs, parent = materialize(work, out)

    def lane(cpu):
        saved = []
        for row in (j for j in jobs if j["cpu"] == cpu):
            name = f"{row['policy']}-{row['workers']}"
            folder = work / name
            whole_iq.checked(folder / "native.json", row["native_sha256"])
            whole_iq.checked(folder / "request.json", row["request_sha256"])
            bracketed_position.launch_case(folder, cpu)
            result, resources = service_result(folder, cpu)
            write(out / f"services/{name}.log", (folder / "service.log").read_bytes())
            saved.append(dict(row, result=result, position_resources=resources))
        return saved

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        positions = [row for lane_rows in pool.map(lane, CPUS) for row in lane_rows]
    (full,) = [
        r
        for r in rows_from(member(PARENT, parent, capture_whole_results.POS))
        if r["method"] == capture_whole.METHOD
    ]
    pack(out / "positions.jsonl.gz", [*positions, full])
    names = (
        "inputs.json",
        "forecasts.json.gz",
        "forecast-lock.json",
        "timing.csv",
        "positions.jsonl.gz",
        *(f"services/{r['policy']}-{r['workers']}.log" for r in jobs),
    )
    save_json(
        out / "prediction-lock.json",
        dict(cases=[full["id"]], files={k: _sha(out / k) for k in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--out", type=local_output, default=REPORT)
    options = parser.parse_args()
    run(options.work, options.out)
