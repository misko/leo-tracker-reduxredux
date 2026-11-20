"""Qualify held whole-IQ optimized replays against fresh archived-factor controls."""

import argparse
import gzip
import json
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, references, save_json, write
from ..scoring import ARMS, validate_result
from . import capture_release, full_held_control, iq_schedule, raw_robust, whole_cavity_scores
from . import whole_fractional as prior
from . import whole_fractional_worker as candidate
from . import whole_memory_chain as apparatus
from .full_v5_check import BULK, NATIVE_LIBRARY, _load_case, _sha
from .prefix_figures import csv_file

REPORT = prior.REPORT.parents[1] / "next/full-held-pair"
RUNS = prior.RUNS.with_name("full-held-pair")
DOMAIN = "full-held-pair-20261119/"
DEVELOPMENT = {"DS26-0036", "DS29-0082"}


def roster(cases):
    hashes = {ident: sha256((DOMAIN + ident).encode()).hexdigest() for ident in sorted(cases)}
    winners = [
        min(
            (ident for ident in hashes if ident.startswith(prefix) and ident not in DEVELOPMENT),
            key=hashes.__getitem__,
        )
        for prefix in ("DS26-", "DS29-")
    ]
    return dict(
        hash_domain=DOMAIN,
        selected=winners,
        ranked=[
            dict(
                id=ident,
                sha256=hashes[ident],
                disposition=(
                    "selected"
                    if ident in winners
                    else "development"
                    if ident in DEVELOPMENT
                    else "hash-rank"
                ),
            )
            for ident in sorted(hashes, key=lambda x: (x[:4], hashes[x]))
        ],
    )


def plan():
    source = prior.REPORT / "source-lock.json"
    earlier = prior.plan()
    if json.loads(source.read_bytes()) != earlier:
        raise ValueError(
            "the optimized detector or complete cavity composition differs from its lock"
        )
    authority_root = prior.whole_pair.REPORT
    archive = authority_root / "archive-authority.json.gz"
    context = json.loads((authority_root / "archive-authority-lock.json").read_bytes())
    ordinary = raw_robust.ORDINARY_RECEIPT
    audit = json.loads(gzip.decompress(archive.read_bytes()))
    if context["files"][archive.name] != _sha(archive) or audit[
        "previous_ordinary_receipts_sha256"
    ] != _sha(ordinary):
        raise ValueError("ordinary archive authority differs from its published lock")
    ordinary_rows = json.loads(ordinary.read_bytes())["recordings"]
    chosen = roster(ordinary_rows)
    paths = [
        Path(__file__),
        Path(full_held_control.__file__),
        REPORT / "PROTOCOL.md",
        source,
        archive,
        ordinary,
        prior.PREFLIGHT,
    ]
    inputs = {}
    known = json.loads(prior.PREFLIGHT.read_bytes())["cases"]
    wrapper_sha = {r["receipt"]["wrapper_sha256"] for r in known.values()}
    for ident in chosen["selected"]:
        c, old = _load_case(ident), ordinary_rows[ident]
        evidence = audit["cases"][ident]
        capture = capture_release.read_capture(c)
        producer = capture_release.producer(c, capture)
        wrapper = producer.root / "leo/analysis/starlink/native_short_window.py"
        base = raw_robust.prior_directory(ident)
        bound, native = base / "experimental-request.json", base / "native.json"
        origin = BULK / c["request"]["path"]
        if (
            capture != evidence["capture"]
            or capture["input_manifest_sha256"] != old["input_manifest_sha256"]
            or _sha(wrapper) not in wrapper_sha
            or _sha(origin) != c["request"]["sha256"]
            or _sha(bound) != old["replay_request_sha256"]
            or _sha(native) != old["native_sha256"]
            or old["detector_sha256"] != "sha256:" + _sha(NATIVE_LIBRARY)
        ):
            raise ValueError(f"held recording {ident} lacks its full ordinary archive authority")
        historical = base / "predictions.jsonl"
        if _sha(historical) != old["prediction_sha256"]:
            raise ValueError("archived ordinary historical wall receipt changed")
        paths.extend(
            (
                wrapper,
                bound,
                native,
                origin,
                historical,
                *(base / f"replayed-{i}.jsonl" for i in range(2)),
            )
        )
        inputs[ident] = dict(
            native_sha256=old["native_sha256"],
            stock_native_path=str(native),
            prior_request_path=str(bound),
            prior_request_sha256=old["replay_request_sha256"],
            stock_lane_path=str(base),
            historical_path=str(historical),
            recording=c["recording"],
            wrapper_sha256=_sha(wrapper),
            capture_era_native_sha256=c["native"]["sha256"],
            catalog_sha256=c["catalog"]["sha256"],
            tile=c["regions"][0],
        )
    return dict(
        earlier,
        inputs=inputs,
        cohort=chosen,
        runtime_max_s=candidate.LIMIT,
        stock_factor_limit_s=full_held_control.LIMIT,
        sources=dict(earlier["sources"]) | {str(p): _sha(p) for p in paths},
    )


def stock(runs, ident, pins):
    r = runs / "control"
    service = json.loads((r / f"{ident}-service.json").read_bytes())
    start = json.loads((r / f"{ident}-begin.json").read_bytes())["start"]
    base = r / ident
    input_path, pos_path = base / "factor-input.json", base / "position-stages.json"
    inputs = json.loads(input_path.read_bytes()) if input_path.exists() else None
    stages = json.loads(pos_path.read_bytes()) if pos_path.exists() else None
    expected = pins["inputs"][ident]
    if stages:
        result = json.loads((base / "position/result.json").read_bytes())
        if (
            not inputs
            or inputs["native_sha256"] != expected["native_sha256"]
            or any(
                item["pid"] != start["pid"]
                or item["cgroup"] != start["cgroup"]
                or item["cpus"] != [candidate.CPUS[0]]
                for item in stages.values()
            )
        ):
            raise ValueError("stock factor control exited its cgroup or historical factor binding")
        wall = stages["end"]["monotonic_s"] - start["monotonic_s"]
    else:
        result = dict(
            status="failed",
            reason=service["systemd"].get("Result", "worker did not finish"),
            arms={a: {"latlon": None} for a in ARMS},
            metrics=dict(position_attempted=(base / "position/request.json").is_file()),
        )
        wall = service["elapsed_s"]
    result["boundary"] = full_held_control.BOUNDARY
    validate_result(result)
    row = dict(
        id=ident,
        method=full_held_control.METHOD,
        mode="matched-tile",
        detector="ordinary",
        native_sha256=expected["native_sha256"],
        input_sha256=expected["native_sha256"],
        catalog_sha256=expected["catalog_sha256"],
        tile=expected["tile"],
        result=result,
        worker_wall_s=wall,
    )
    return row, dict(
        service=service,
        start=start,
        factor_input=inputs,
        position=stages,
        service_log=(r / f"{ident}-systemd.log").read_text(),
    )


def archived_timing(inputs):
    output = json.loads(Path(inputs["historical_path"]).read_bytes())
    counters = {"segments": 0, "detector_cpu_s": 0.0}
    for lane in range(2):
        with (Path(inputs["stock_lane_path"]) / f"replayed-{lane}.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                if row["kind"] == "segment":
                    counters["segments"] += 1
                    counters["detector_cpu_s"] += row["detector_cpu_s"]
    return dict(
        counters,
        boundary="Historical raw and assembly replay, different original position path",
        raw_and_assembly_wall_s=output["result"]["metrics"].get("raw_and_assembly_wall_s"),
        historical_pipeline_wall_s=output["worker_wall_s"],
    )


def run(runs, ident, selected):
    pins = json.loads((runs / "plan.json").read_bytes())
    if pins != plan() or ident not in pins["cohort"]["selected"]:
        raise ValueError("requested recording or source differs from the prospective selection")
    if selected is candidate and not (runs / "control" / f"{ident}-service.json").is_file():
        raise ValueError("run the authenticated stock factor control first")
    tmp = runs / "tmp"
    launch = apparatus.subprocess.Popen

    def bounded_launch(command, *args, **kwargs):
        if command[0] == "systemd-run":
            command = [command[0], f"--setenv=TMPDIR={tmp}", *command[1:]]
        return launch(command, *args, **kwargs)

    with (
        patch.multiple(apparatus, chain=selected, plan=plan),
        patch.object(apparatus.subprocess, "Popen", bounded_launch),
    ):
        apparatus.run(ident, runs if selected is candidate else runs / "control")


def publish(runs, report):
    pins = json.loads((runs / "plan.json").read_bytes())
    if pins != plan():
        raise ValueError("the prospective archive or source lock changed")
    ids = [i for i in pins["cohort"]["selected"] if (runs / f"{i}-service.json").is_file()]
    if not ids:
        raise ValueError("no held whole-IQ outcomes")
    traces, comparisons, originals, fresh = {}, {}, [], []
    with patch.multiple(apparatus, chain=candidate, control=lambda i: stock(runs, i, pins)[0]):
        for ident in ids:
            original, archived = stock(runs, ident, pins)
            new, trace = apparatus.summarize(runs, ident)
            raw = trace["raw"] or {}
            new["origin_native_sha256"] = original["native_sha256"]
            new["native_sha256"] = raw.get("native_sha256")
            new["input_sha256"] = new["native_sha256"]
            originals.append(original)
            fresh.append(new)
            traces[ident] = dict(factor_control=archived, optimized_whole_iq=trace)
            comparisons[ident] = dict(
                raw_factor_parity=raw.get("factor_parity"),
                literal_lanes=raw.get("lane_parity"),
                request_parity=raw.get("request_parity"),
                exact_endpoint_and_rms=trace["exact_endpoints_and_radio"],
                ordinary_control_status=original["result"]["status"],
                historical_iq=archived_timing(pins["inputs"][ident]),
                optimized_native=iq_schedule.native_durations(trace),
            )
    save_json(report / "source-lock.json", pins)
    save_json(report / "comparison.json", comparisons)
    for f, content in (
        ("positions.jsonl.gz", b"".join(encoded(r) + b"\n" for r in fresh)),
        ("control-positions.jsonl.gz", b"".join(encoded(r) + b"\n" for r in originals)),
        ("stages.json.gz", encoded(traces)),
    ):
        write(report / f, gzip.compress(content, mtime=0))
    files = (
        "positions.jsonl.gz",
        "control-positions.jsonl.gz",
        "stages.json.gz",
        "comparison.json",
        "cohort.json",
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=ids,
            files={f: _sha(report / f) for f in files},
            source_lock_sha256=_sha(report / "source-lock.json"),
        ),
    )
    truth = {r["id"]: r["truth"] for r in references("roof16", ids)[1]}
    scores = [
        dict(s, method=row["method"])
        for row in (*fresh, *originals)
        for s in whole_cavity_scores.arm_scores(row, truth[row["id"]])
    ]
    csv_file(report / "scores.csv", scores)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("seal", "control", "replay", "publish"))
    p.add_argument("--case")
    p.add_argument("--runs", type=local_output, default=RUNS)
    args = p.parse_args()
    if args.action == "seal":
        args.runs.mkdir(parents=True, exist_ok=False)
        (args.runs / "control").mkdir()
        (args.runs / "tmp").mkdir()
        pins = plan()
        for folder in (args.runs, args.runs / "control"):
            save_json(folder / "plan.json", pins)
        save_json(REPORT / "cohort.json", pins["cohort"])
    elif args.action == "publish":
        publish(args.runs, REPORT)
    else:
        run(args.runs, args.case, full_held_control if args.action == "control" else candidate)


if __name__ == "__main__":
    main()
