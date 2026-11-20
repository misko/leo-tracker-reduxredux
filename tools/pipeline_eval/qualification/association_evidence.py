"""Bind actual Graph tracks and joint replay decisions to the final original v5 owners."""

import gzip
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from ..__main__ import ROOT, encoded, read_predictions, save_json, write
from ..reference.native_archive import NativeArchive
from . import native_joint_trial as trial
from . import phase_confirmation as phase
from .v5_postfit import _map
from .v5_prefix_audit import value

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/factors/association-evidence"
CASES = {"DS26-0223": 1, "DS29-0316": 21}
ALL = ("DS26-0197", *CASES)
WORKER = Path(__file__).with_name("association_evidence_worker.py")


def digest(raw):
    return sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def original(ident, item):
    archive = phase.ARCHIVE if ident.startswith("DS26-") else phase.DS29
    folder = archive / (ident + "-r0")
    receipt = folder / "baseline-execution.json"
    execution = read(receipt)
    package = folder / "baseline/experimental-evidence.zip"
    content = phase.digest(package)
    if execution["worker"]["artifact"]["sha256"] != "sha256:" + content:
        raise ValueError("original published checkpoint digest mismatch")
    with ZipFile(package) as z:
        tree = _map(json.loads(z.read("values.json"))["tree"])
        request = _map(tree["request"])
        job = _map(request["job"])
        if (
            tree["request_sha256"] != execution["request_sha256"]
            or _map(job["native_input"])["sha256"] != "sha256:" + item["native"]["sha256"]
        ):
            raise ValueError("published ownership belongs to another native capture")
        selected = _map(tree["selected"])
        owners = {arm: _map(x) for arm, x in _map(selected["owners"]).items()}
        positions = {
            arm: value(_map(x)["endpoint_latlon"], z) for arm, x in _map(selected["arms"]).items()
        }
    return dict(
        execution_sha256=phase.digest(receipt),
        artifact_sha256=content,
        request_sha256=execution["request_sha256"],
        owners=owners,
        positions=positions,
    )


def graph_points(path, expected, source, tracks):
    by_time = {}
    for i, track in enumerate(tracks):
        lane = track["receiver"], track["channel"], track["rf_hz"]
        for t in track["times"]:
            key = (*lane, t)
            if key in by_time:
                raise ValueError("unexpected shared Graph point")
            by_time[key] = i
    points = []
    with path.open(encoding="ascii") as raw:
        native = NativeArchive(raw)
        for t, text in native:
            row = json.loads(text)
            rx, ch, rf, counter = (
                row[k] for k in ("receiver_id", "channel", "actual_rf_hz", "valid_start_counter")
            )
            accepted = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
            if not accepted:
                continue
            winner = max(accepted, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]))
            point_id = "sha256:" + digest(f"{source}:{rx}:{counter}".encode())
            points.append(
                dict(
                    id=point_id,
                    t=t,
                    receiver=rx + 1,
                    channel=ch,
                    rf_hz=rf,
                    wrapped_hz=winner["fractional_tracking_cfo_hz"],
                    margin=winner["fractional_margin"],
                    rank=winner["candidate_rank"],
                    alternative_peaks=len(row["candidates"]) - 1,
                    counter=counter,
                    visit=row["visit_index"],
                    graph_track=by_time.get((rx + 1, ch, rf, t)),
                )
            )
    if phase.digest(path) != expected or sum(p["graph_track"] is not None for p in points) != len(
        by_time
    ):
        raise ValueError("native clock and exact Graph points did not recover every input")
    return points


def inventory(trace, points, publication):
    tracks = trace["observation"]["tracks"]
    norad = trace["banks"][1]
    train, pool = trace["training"][0], trace["all_associations"][-1]
    pooled = {row["track"]: row for row in pool if row["loss"] <= 6.25}
    earlier = {row["track"]: row for row in train["owners"]}
    by_graph = {}
    for row in points:
        row["v5_c0"] = publication["owners"]["c0"].get(row["id"])
        row["v5_fitted_c"] = publication["owners"]["fitted_c"].get(row["id"])
        if row["graph_track"] is not None:
            by_graph.setdefault(row["graph_track"], []).append(row)
    rows = []
    for arc in trace["arcs"]:
        k = arc["index"]
        section = by_graph[k]
        observed = tracks[k]
        before, after = earlier.get(k), pooled.get(k)
        r0, r1 = (norad[r["orbit"]] if r is not None else None for r in (before, after))
        c0 = Counter(p["v5_c0"] for p in section if p["v5_c0"] is not None)
        fit = Counter(p["v5_fitted_c"] for p in section if p["v5_fitted_c"] is not None)
        dominant, support = c0.most_common(1)[0] if c0 else (None, 0)
        disagrees = dominant is not None and support >= len(section) // 2 and dominant != r1
        change = r0 is not None and r1 is not None and r0 != r1
        rows.append(
            dict(
                **arc,
                unique_points=len(section),
                duration_s=observed["times"][-1] - observed["times"][0],
                joint_train=r0,
                joint_pool=r1,
                pooled=after,
                trained=before,
                v5_c0=dict(c0.most_common()),
                v5_fitted_c=dict(fit.most_common()),
                disputed=bool(r1 is None or change or disagrees),
                identity_change=change,
            )
        )
    selected = min(
        (r for r in rows if r["curved"] and r["disputed"]),
        key=lambda r: (-r["unique_points"], -r["duration_s"], r["index"]),
    )
    return rows, selected


def replay(ident, cases, archived):
    item = cases[ident]
    packet, paths = trial.native.request(item, "native")
    raw = encoded(packet)
    if archived["input_sha256"] != digest(raw):
        raise ValueError("joint replay request differs from the frozen report")
    command = trial.command(CASES[ident], paths, trial.BUNDLE)
    command[command.index(str(trial.WORKER))] = str(WORKER)
    proc = subprocess.run(command, input=raw, capture_output=True, timeout=75, check=True)
    out = json.loads(proc.stdout)
    a, b = out["result"], archived["result"]
    if (
        out["observation_sha256"] != archived["observation_sha256"]
        or a["arms"] != b["arms"]
        or a["reason"] != b["reason"]
        or {k: v for k, v in a["metrics"].items() if not k.endswith("_s")}
        != {k: v for k, v in b["metrics"].items() if not k.endswith("_s")}
    ):
        raise ValueError("trace changed the original native joint solution")
    published = original(ident, item)
    trace = out["trace"]
    points = graph_points(
        paths["native"],
        item["native"]["sha256"],
        item["session_id"],
        trace["observation"]["tracks"],
    )
    rows, selected = inventory(trace, points, published)
    out.update(
        published={k: v for k, v in published.items() if k != "owners"},
        track_inventory=rows,
        selected=selected,
        packet=packet,
        native_points=points,
        id=ident,
    )
    write(OUTPUT / f"{ident}-native-trace.json.gz", gzip.compress(encoded(out), mtime=0))
    print(ident, "frozen joint exact", selected, flush=True)


def main():
    catalogue = trial.REPORT / "positions.jsonl.gz"
    lock = read(trial.REPORT / "prediction-lock.json")
    if lock["files"][catalogue.name] != phase.digest(catalogue):
        raise ValueError("archived joint predictions do not match their seal")
    records = read_predictions(catalogue)
    cases = phase.frozen_inputs()
    save_json(
        OUTPUT / "run_manifest.json",
        dict(
            source={
                str(path.relative_to(ROOT)): phase.digest(path) for path in (Path(__file__), WORKER)
            },
            frozen_joint=trial.sources(trial.BUNDLE),
            cases={k: records[k]["input_sha256"] for k in ALL},
            joint_prediction_sha256=phase.digest(catalogue),
            protocol_sha256=phase.digest(OUTPUT / "PROTOCOL.md"),
            commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            cpus=CASES,
            alias_hz=1 / 4.4e-6,
            sample_rate_hz=10_000_000,
            integration_s=0.020,
        ),
    )
    save_json(
        OUTPUT / "geometry-gates.json",
        {
            k: dict(
                reason=records[k]["result"]["reason"],
                pooled_shift_km=records[k]["result"]["metrics"]["pooled_shift_km"],
                posterior_radius_km={
                    a: r["radius_km"] for a, r in records[k]["result"]["arms"].items()
                },
                shift_limit_km=4,
                radius_limit_km=6,
            )
            for k in ALL
        },
    )
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda ident: replay(ident, cases, records[ident]), CASES))


if __name__ == "__main__":
    main()
