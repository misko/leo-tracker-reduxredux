"""Replay the compact secant policy on archived truth-free offers and an authentic shift."""

import argparse
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

from ..__main__ import encoded, local_output, save_json, write
from ..scoring import validate_result
from ..variants import orbit_projector, portable_v5, v5_secant_fit
from . import clock_transfer as prior
from . import portable_v5_trials as portable
from .fresh_scenes import _destination, _read, _sha
from .portable_gate_trials import invoke, worker_command
from .portable_v5_transfer import simulated_document

REPORT = prior.REPORT.parents[1] / "redesign/compact-transfer"
WORKER = Path(__file__).with_name("compact_transfer_worker.py")
CASES = (
    ("29a0b6f54f7cfefd1dc29bd6", "806c67257735af45899f6fc6"),
    ("2b44a477e9d80e6241410da1", "29acc1a0b130b052ca072c73"),
)
ROOF = "DS26-0036-7km-east"
METHOD = "v5_secant_transfer"
CAP = 225


def complete_native(document):
    source = document["source"]
    clock = document["clock_anchor"]
    first = clock["sample_counter"]
    anchor = clock["before"]["realtime_ns"]
    if anchor != clock["after"]["realtime_ns"]:
        raise ValueError("synthetic supplement requires the existing exact simulated anchor")
    result = simulated_document(source["session_id"], anchor, source["probes"], first)
    if result["last_sample_counter"] != document["last_sample_counter"]:
        raise ValueError("synthetic sample bound differs from the sealed native capture")
    for key in ("before", "after"):
        result["clock_anchor"][key] = dict(realtime_ns=anchor, monotonic_ns=10_000_000_000)
    for key in ("probe_ms", "probes", "sample_rate_hz", "session_id"):
        if source[key] != result["source"][key]:
            raise ValueError("portable supplement changed sealed native observations")
    return result


def history_at(cutoff, expected_sha):
    scenes = prior.custodian.cold
    when = datetime.fromtimestamp(
        cutoff / scenes.NS, tz=datetime.fromisoformat("2026-11-15T00:00:00+00:00").tzinfo
    )
    root = scenes.SNAPSHOT.parents[3]
    stamps, inventory, objects = [], [], {}
    for i in range(4):
        date = when - timedelta(days=i)
        for manifest in sorted((root / date.strftime("%Y/%m/%d")).glob("*.json")):
            entry = _read(manifest)
            received = scenes._stamp(datetime.fromisoformat(entry["retrieved_at"]))
            newest = scenes._stamp(datetime.fromisoformat(entry["tle_epoch_max"]))
            if not cutoff - 72 * portable_v5.NS_HOUR <= received <= cutoff or newest > received:
                continue
            sha = entry["raw_sha256"]
            path = scenes.TLE_ARCHIVE / entry["raw_object"]
            if sha not in objects and _sha(path) != sha:
                raise ValueError("authentic snapshot disagrees with its bound object digest")
            objects[sha] = path
            stamps.append(dict(collected_utc_ns=received, sha256=sha))
            inventory.append(
                dict(
                    collected_utc_ns=received,
                    sha256=sha,
                    manifest_sha256=_sha(manifest),
                    manifest=str(manifest.relative_to(scenes.TLE_ARCHIVE)),
                )
            )
    stamps = portable.preferred_history(stamps, cutoff)
    if not stamps or stamps[-1]["sha256"] != expected_sha:
        raise ValueError("portable causal history does not terminate with the shared bound TLE")
    return stamps, objects, inventory


def request_data(document, offer, history):
    clean = portable_v5.native_input(document)
    tile = {k: offer[k] for k in ("id", "center", "width_km")}
    stamps = [{k: r[k] for k in ("collected_utc_ns", "sha256")} for r in history]
    return encoded(dict(document=clean, tile=tile, history=stamps))


def run_one(row, data, objects, kernel, cpu):
    command = worker_command(cpu, objects, kernel, WORKER, modules=(v5_secant_fit,))
    package = Path(v5_secant_fit.__file__).parent.parent
    for name in ("__main__.py", "scoring.py"):
        command[-4:-4] = ("--ro-bind", str(package / name), f"/worker/tools/pipeline_eval/{name}")
    stdout, stderr, status, elapsed = invoke(["nice", "-n", "12", *command], data, CAP)
    trace, errors = [], []
    for line in stderr.decode(errors="replace").splitlines():
        try:
            trace.append(json.loads(line))
        except ValueError:
            errors.append(line)
    if status == "complete":
        result = json.loads(stdout)
    else:
        reason = errors[-1] if errors else f"compact secant {status} after {CAP} s"
        result = portable_v5.unavailable(reason) | {"status": status}
    validate_result(result)
    print(row["id"], result["status"], round(elapsed, 1), flush=True)
    return dict(row, method=METHOD, result=result, trace=trace, wall_s=elapsed, cpu=cpu)


def bound_job(row, document, tile, stamps, objects):
    data = request_data(document, tile, stamps)
    return (
        dict(
            row,
            tile=tile,
            worker_input_sha256=prior.custodian.cold._sha(data),
            history_sha256=prior.custodian.cold._sha(encoded(stamps)),
        ),
        data,
        objects,
    )


def prepare(panel):
    source = _read(panel / "input-lock.json")["public"]
    if source["public/requests.json"] != _sha(panel / "public/requests.json"):
        raise ValueError("sealed transfer offers have changed")
    requests = {r["id"]: r for r in _read(panel / "public/requests.json")}
    config = panel / "public/track-config.json"
    if (
        _sha(config) != source["public/track-config.json"]
        or _read(config)["config"] != portable_v5.TRACK_CONFIG
    ):
        raise ValueError("portable native track configuration differs from the shared panel")
    lanes, inventory = [], {}
    for pair in CASES:
        rows = [requests[i] for i in pair]
        capture = rows[0]["capture_id"]
        record = panel / f"public/{capture}.json"
        earlier = rows[0]["packet"]["catalogue"]["sha256"]
        if source[f"public/{capture}.json"] != _sha(record):
            raise ValueError("sealed native input has changed")
        document = complete_native(_read(record))
        cutoff = document["clock_anchor"]["before"]["realtime_ns"]
        stamps, objects, inventory[capture] = history_at(cutoff, earlier)
        jobs = []
        for row in rows:
            pkt = row["packet"]
            metadata = dict(
                id=row["id"],
                capture_id=capture,
                native_sha256=pkt["native"]["sha256"],
                catalog_sha256=pkt["catalogue"]["sha256"],
            )
            if (
                row["capture_id"] != capture
                or pkt["native"]["sha256"] != _sha(record)
                or pkt["catalogue"]["sha256"] != earlier
                or pkt["cutoff"] != cutoff
            ):
                raise ValueError("the offered pair changed shared native or TLE inputs")
            jobs.append(bound_job(metadata, document, pkt["offer"], stamps, objects))
        lanes.append(jobs)

    roof_doc, original, stamps, objects, _, stock = portable.authentic_roof()
    roof_offer = dict(
        original, id=ROOF, center=_destination(original["center"], 7.0, 1.5707963267948966)
    )
    roof_native = stock["native_sha256"].removeprefix("sha256:")
    roof_catalogue = portable._load_case(portable.ROOF_CASE)["catalog"]["sha256"]
    metadata = dict(
        id=ROOF,
        capture_id=portable.ROOF_CASE,
        native_sha256=roof_native,
        catalog_sha256=roof_catalogue,
    )
    lanes[0].append(bound_job(metadata, roof_doc, roof_offer, stamps, objects))
    inventory[ROOF] = stamps
    return lanes, inventory


def replay(panel, scratch, output):
    if (output / "prediction-lock.json").exists():
        raise ValueError("choose a separate output for a new compact prediction seal")
    scratch.mkdir(parents=True, exist_ok=True)
    scientific = portable.source_lock() | {
        p.name: _sha(p)
        for p in (Path(__file__), WORKER, Path(v5_secant_fit.__file__), output / "PROTOCOL.md")
    }
    lanes, inventory = prepare(panel)
    save_json(output / "source-lock.json", scientific)
    save_json(output / "history-inventory.json", inventory)
    plan = [row for batch in lanes for row, _, _ in batch]
    save_json(output / "requests.json", plan)
    kernel = scratch / "projector.so"
    orbit_projector.compile_kernel(kernel)

    def run(cpu, jobs):
        return [run_one(row, data, objects, kernel, cpu) for row, data, objects in jobs]

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = [r for lane in pool.map(run, (13, 14), lanes) for r in lane]
    write(
        output / "predictions.jsonl.gz",
        gzip.compress(b"".join(encoded(row) + b"\n" for row in records), mtime=0),
    )
    names = ("predictions.jsonl.gz", "history-inventory.json", "requests.json", "source-lock.json")
    save_json(
        output / "prediction-lock.json",
        dict(
            files={name: _sha(output / name) for name in names},
            cases=[r["id"] for r in plan],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("panel", type=Path)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--out", default=REPORT, type=Path)
    args = parser.parse_args()
    replay(args.panel, local_output(args.scratch), local_output(args.out))
