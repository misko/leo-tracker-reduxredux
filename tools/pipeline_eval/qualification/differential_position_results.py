"""Audit installed Graph support and score the sealed differential position replay."""

import argparse
import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from .. import whole_iq
from ..__main__ import THREAD_ENV, local_output, save_json
from ..scoring import ARMS, distance_km
from . import differential_position as trial
from . import screening_figures
from .bracketed_position_results import V5_OPTIONS
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

GRAPH_PROCESS = """
import json, sys
root, native, digest, config = sys.argv[1:]
sys.path.insert(0, root)
from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from tools.pipeline_eval.variants.direct_lifetime_kernels import prepare_owned, read_native
document = read_native(dict(path=native, sha256='sha256:' + digest))
session = document['source']['session_id']
prepared = prepare_owned(prepare_tracks, document, TrackConfig(**json.load(open(config))['config']))
print(json.dumps(dict(
    session=session, status=prepared['status'],
    winners={x['observation_id']:x['measured_cfo_hz'] for x in prepared['observations']},
    tracks=[dict(id=t['key'], members=t['observation_ids'], quality=t['quality_status'],
                 curved=i in prepared['curved_indices'], start_s=t['start_s'], end_s=t['end_s'])
            for i,t in enumerate(prepared['tracks'])],
)))
"""
LABEL = {"stock": "Stock wide phase-release", "causal": "Blind rank-one hint", "sham": "Sham hint"}
FIGURE_ID = "differential-partial-iq-position"


def graph_members(record):
    members = {}
    for track in record["tracks"]:
        for point in track["members"]:
            if point in members:
                raise ValueError("Graph membership is not unique")
            members[point] = track
    return members


def graph_point(site, row, members):
    plain = f"{site['session']}:{row['receiver']}:{row['counter']}"
    ident = "sha256:" + sha256(plain.encode()).hexdigest()
    value = site["winners"].get(ident)
    if value != row["winner_cfo_hz"]:
        raise ValueError("installed Graph winner did not match its raw probe receipt")
    track = members.get(ident)
    return dict(
        row,
        observation_id=ident,
        graph_id=track["id"] if track else None,
        graph_point_count=len(track["members"]) if track else None,
        graph_span_s=track["end_s"] - track["start_s"] if track else None,
        graph_quality=track["quality"] if track else None,
        graph_curved=track["curved"] if track else False,
    )


def graph_audit(work, report, prediction):
    lock = trial.selection(work, report)
    graph = {}
    for ident, spec in lock["cases"].items():
        config = spec["config"]
        whole_iq.checked(Path(config["path"]), config["sha256"])
        for mode, mode_spec in spec["modes"].items():
            native = work / ident / mode / "native.json"
            digest = mode_spec["native_sha256"]
            if digest != prediction[ident, mode]["native_sha256"]:
                raise ValueError("Graph audit does not bind actual prediction inputs")
            command = [
                "taskset",
                "-c",
                str(spec["cpu"]),
                sys.executable,
                "-IB",
                "-c",
                GRAPH_PROCESS,
                lock["receiver"],
                str(native),
                digest,
                config["path"],
            ]
            raw = subprocess.check_output(command, env={**os.environ, **THREAD_ENV}, timeout=40)
            graph[ident, mode] = json.loads(raw)
    members = {key: graph_members(value) for key, value in graph.items()}
    points = []
    for row in rows_from(report / "window-audit.jsonl.gz"):
        key = row["id"], row["mode"]
        points.append(graph_point(graph[key], row, members[key]))
    summaries = []
    for (ident, mode), result in graph.items():
        base = graph[ident, "stock"]
        baseline = members[ident, "stock"]
        actual = members[ident, mode]
        distinct = [r for r in points if (r["id"], r["mode"]) == (ident, mode) and r["changed"]]
        curves = [t for t in result["tracks"] if t["curved"]]
        metrics = prediction[ident, mode]["result"]["metrics"]
        if metrics and (
            metrics["observations"] != len(result["winners"])
            or metrics["tracks"] != len(result["tracks"])
        ):
            raise ValueError("independent installed Graph disagrees with receiver counters")
        summaries.append(
            dict(
                id=ident,
                mode=mode,
                status=result["status"],
                winners=len(result["winners"]),
                winner_gained=len(result["winners"].keys() - base["winners"].keys()),
                winner_lost=len(base["winners"].keys() - result["winners"].keys()),
                winner_cfo_changed=sum(
                    result["winners"][p] != base["winners"][p]
                    for p in result["winners"].keys() & base["winners"].keys()
                ),
                tracks=len(result["tracks"]),
                graph_points=len(actual),
                graph_points_gained=len(actual.keys() - baseline.keys()),
                graph_points_lost=len(baseline.keys() - actual.keys()),
                curves=len(curves),
                curved_points=sum(len(t["members"]) for t in curves),
                edited_probes=len(distinct),
                edited_graph_points=sum(r["graph_id"] is not None for r in distinct),
                edited_curved_points=sum(r["graph_curved"] for r in distinct),
            )
        )
    pack(
        report / "graph-tracks.jsonl.gz", [dict(id=k[0], mode=k[1], **v) for k, v in graph.items()]
    )
    csv_file(report / "graph-probes.csv", points)
    csv_file(report / "graph-support.csv", summaries)
    return {(r["id"], r["mode"]): r for r in summaries}


def scores(prediction, references, graph, resources):
    for ref in references:
        ident = ref["id"]
        for arm in ARMS:
            control = prediction[ident, "stock"]["result"]["arms"][arm]
            stock_error = distance_km(control["latlon"], ref["truth"])
            for mode in trial.MODES:
                fit = prediction[ident, mode]["result"]
                endpoint = fit["arms"][arm]
                pos = endpoint["latlon"]
                error = distance_km(pos, ref["truth"])
                resource = resources[ident][mode]
                yield dict(
                    id=ident,
                    arm=arm,
                    method=trial.METHODS[mode],
                    status=fit["status"],
                    latitude=pos[0] if pos else None,
                    longitude=pos[1] if pos else None,
                    error_km=error,
                    shift_from_stock_km=distance_km(pos, control["latlon"]),
                    error_change_km=error - stock_error
                    if error is not None and stock_error is not None
                    else None,
                    rms_hz=endpoint.get("rf_rms_hz"),
                    conditional_frequency_score=fit["metrics"].get(f"{arm}_frequency_score"),
                    position_wall_s=resource.get("wall_s"),
                    position_cpu_s=resource.get("cpu_s"),
                    position_peak_bytes=resource.get("peak_bytes"),
                    cavity_offered=fit["metrics"].get("cavity_offered"),
                    **{
                        k: v
                        for k, v in graph[ident, mode].items()
                        if k not in ("id", "status", "mode")
                    },
                )
            for mode in V5_OPTIONS:
                fit = ref["reference"][mode][arm]
                pos = fit.get("latlon")
                yield dict(
                    id=ident,
                    arm=arm,
                    method=mode,
                    status=fit["status"],
                    latitude=pos[0] if pos else None,
                    longitude=pos[1] if pos else None,
                    error_km=fit["error_km"],
                    rms_hz=fit.get("rf_rms_hz"),
                )


def publish(work, report):
    path = report / "prediction-lock.json"
    lock = whole_iq.read(path)
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    rows = rows_from(report / "positions.jsonl.gz")
    mode_of = {v: k for k, v in trial.METHODS.items()}
    prediction = {(row["id"], mode_of[row["method"]]): row for row in rows}
    cases = lock["cases"]
    if len(rows) != len(prediction) or prediction.keys() != {
        (ident, mode) for ident in cases for mode in trial.MODES
    }:
        raise ValueError("prediction seal has an incomplete or repeated trial")
    provenance = [
        "prediction-lock.json",
        "source-lock.json",
        "window-audit.jsonl.gz",
        "resources.json",
        "graph-tracks.jsonl.gz",
        "graph-probes.csv",
        "graph-support.csv",
        "scores.csv",
    ]
    graph = graph_audit(work, report, prediction)
    _, refs = held_references(None, cases)
    csv_file(
        report / "scores.csv",
        list(scores(prediction, refs, graph, whole_iq.read(report / "resources.json"))),
    )
    seal = "figure-lock.json"
    save_json(
        report / seal,
        dict(
            cases=cases,
            files={name: _sha(report / name) for name in [*provenance, "positions.jsonl.gz"]},
            exporter_sha256=_sha(Path(__file__)),
        ),
    )
    paired = ["stock_native_sha256", "catalog_sha256", "tile", "original_request_sha256"]
    save_json(
        report / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=FIGURE_ID,
                    method=trial.METHODS["causal"],
                    scope="roof",
                    cases=cases,
                    seal=seal,
                    provenance=provenance,
                    title="Differential pilot timing on 32 scheduled raw windows",
                    caption=(
                        "Eight visits per recording substitute real stock, blind rank-one or sham "
                        "packets. All other visits retain stock wide factors. The four original v5 "
                        "options use archived capture-era factors at the same roof."
                    ),
                    series=[
                        dict(
                            key=key,
                            label=LABEL[mode],
                            file="positions.jsonl.gz",
                            value=trial.METHODS[mode],
                            native_field="capture_era_native_sha256",
                            **({"match": paired} if key != "one" else {}),
                        )
                        for key, mode in (
                            ("one", "causal"),
                            ("stock", "stock"),
                            ("one_native_factors", "sham"),
                        )
                    ],
                )
            ],
        ),
    )
    screening_figures.generate(report / "charts", methods=[FIGURE_ID], evidence=report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, type=local_output)
    parser.add_argument("--out", default=trial.REPORT, type=local_output)
    args = parser.parse_args()
    publish(args.work, args.out)


if __name__ == "__main__":
    main()
