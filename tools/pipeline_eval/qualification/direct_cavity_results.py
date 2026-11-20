"""Seal and score the staged compact cavity receiver and compact secant control."""

import argparse
import gzip
import io
import json
import tarfile
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import direct_cavity_trial as trial
from . import full_receiver_comparison as common
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

FILES = {trial.DIRECT: "positions.jsonl.gz", trial.STOCK: "stock-positions.jsonl.gz"}
GROUPS = ("ordinary", "capture-era", "held")
WORK = (
    "initial_branches",
    "initial_arm_fits",
    "cavity_offered",
    "observations",
    "tracks",
    "compact_projections",
)


def pack_release(stage, bundle, out):
    """Package the staged bytes without host-specific binary or path bindings."""
    name = "compact-cavity-source.tar.gz"
    entries = common.read(bundle)["files"]
    memory = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=memory, mode="wb", mtime=0) as stream,
        tarfile.open(fileobj=stream, mode="w|", format=tarfile.PAX_FORMAT) as archive,
    ):
        for path, digest in sorted(entries.items()):
            source = stage / path
            if common.sha(source) != digest:
                raise ValueError(f"staged science release changed: {path}")
            data = source.read_bytes()
            item = tarfile.TarInfo(path)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    write(out / name, memory.getvalue())
    return name


def seal(work, out):
    path = work / "plan.json"
    plan = common.read(path)
    if plan["sources"] != trial.sources():
        raise ValueError("original or new numerical source changed")
    out.mkdir(parents=True, exist_ok=True)
    rows = {method: [] for method in FILES}
    for key, (cpu, order) in plan["cases"].items():
        binding = plan["bindings"][key]
        group = "held" if binding["id"] == plan["held"]["id"] else binding["detector"]
        for i, method in enumerate(order):
            receipt = work / "runs" / key / method / "prediction.json"
            if not receipt.is_file():
                raise FileNotFoundError(f"No completed attempt receipt {receipt}")
            expected = dict(
                binding, cpu=cpu, order=i, key=key, method=method, plan_sha256=common.sha(path)
            )
            row = common.read(receipt)
            common.require_fields(row, expected)
            validate_result(row["result"])
            rows[method].append(dict(row, cohort=group))
    for method, name in FILES.items():
        pack(out / name, rows[method])
    write(out / "source-lock.json", path.read_bytes())
    bundle = work / "bundle.json"
    if common.sha(bundle) != plan["bundle_sha256"]:
        raise ValueError("release file manifest changed")
    write(out / "bundle.json", bundle.read_bytes())
    release = pack_release(work / trial.RELEASE, bundle, out)
    names = (*FILES.values(), "bundle.json", release)
    save_json(
        out / "receipt.json",
        dict(
            cases=[row["id"] for row in rows[trial.DIRECT]],
            files={name: common.sha(out / name) for name in names},
            source_lock_sha256=common.sha(out / "source-lock.json"),
        ),
    )


def parity(stock, direct):
    common.require_fields(direct, {k: stock[k] for k in trial.MATCH})
    a, b = stock["result"], direct["result"]
    output = dict(stock_status=a["status"], direct_status=b["status"])
    if a["status"] == b["status"] == "ok":
        output.update(
            coordinates={key: a["arms"][key]["latlon"] == b["arms"][key]["latlon"] for key in ARMS},
            conditional_rms={
                key: a["arms"][key]["rf_rms_hz"] == b["arms"][key]["rf_rms_hz"] for key in ARMS
            },
            counts={
                k: k in a["metrics"] and k in b["metrics"] and a["metrics"][k] == b["metrics"][k]
                for k in WORK
            },
        )
    return output


def score(out):
    seal = common.seal(out, "receipt.json", FILES.values())
    data = {method: read_predictions(out / name) for method, name in FILES.items()}
    truth, _ = _frozen_roof()
    scores, timings, comparisons = [], [], {}
    for ident in seal["cases"]:
        left, right = data[trial.STOCK][ident], data[trial.DIRECT][ident]
        comparisons[ident] = parity(left, right)
        for row in (left, right):
            result = row["result"]
            tag = dict(id=ident, group=row["cohort"], method=row["method"], status=result["status"])
            timings.append(
                dict(
                    tag,
                    cpu=row["cpu"],
                    order=row["order"],
                    **row["resources"],
                    **{f"{k}_s": v for k, v in result["metrics"].get("stage_s", {}).items()},
                )
            )
            for arm in ARMS:
                ref = result["arms"][arm]
                scores.append(
                    dict(
                        tag,
                        arm=arm,
                        error_km=distance_km(ref["latlon"], truth[ident]["truth"]),
                        conditional_rms_hz=ref.get("rf_rms_hz"),
                        frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    files = ("scores.csv", "timings.csv", "parity.json")
    for name, rows in zip(files[:2], (scores, timings), strict=True):
        keys = tuple(dict.fromkeys(k for row in rows for k in row))
        csv_file(out / name, [{k: row.get(k) for k in keys} for row in rows])
    save_json(out / files[2], comparisons)
    figures = []
    for group in GROUPS:
        cases = [i for i in seal["cases"] if data[trial.DIRECT][i]["cohort"] == group]
        receipt = f"{group}-lock.json"
        save_json(
            out / receipt,
            dict(
                cases=cases,
                source_lock_sha256=seal["source_lock_sha256"],
                files={**seal["files"], **{f: common.sha(out / f) for f in files}},
            ),
        )
        figures.append(
            dict(
                id=f"direct-cavity-{group}",
                method=trial.DIRECT,
                scope="roof",
                cases=cases,
                seal=receipt,
                title=f"Direct compact v5 cavity · {group}",
                caption=(
                    "Fresh same-core runs use identical native factors, causal history and offer. "
                    "Capture-era held input selected by archive-time stratum and salted hash."
                    if group == "held"
                    else "Fresh same-core runs use identical native factors, "
                    "causal history and offer through compact cavity."
                ),
                provenance=list(files),
                source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                series=[
                    dict(
                        key=key,
                        value=method,
                        file=FILES[method],
                        label=label,
                        where={"cohort": group},
                        native_authority="ordinary" if group == "ordinary" else "frozen",
                        **({"match": list(trial.MATCH)} if method == trial.STOCK else {}),
                    )
                    for key, method, label in (
                        ("one", trial.DIRECT, "Direct staged entry"),
                        ("stock", trial.STOCK, "Original compact secant"),
                    )
                ],
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=figures))


def trace_summary(work, out):
    data, summary = {}, {}
    for tag, method in (("stock", trial.STOCK), ("direct", trial.DIRECT)):
        folder = work / "trace" / tag
        reach, measurement = folder / "reach.json", folder / "measurement.json"
        if not reach.is_file() or not measurement.is_file():
            continue
        traced = common.read(measurement)
        base = read_predictions(out / FILES[method])["DS29-0082"]
        common.require_fields(traced, {k: base[k] for k in trial.MATCH})
        report = common.read(reach)
        status = traced["result"]["status"]
        category = (
            "cavity_policy"
            if traced["result"]["metrics"].get("cavity_offered")
            else "signed_context"
        )
        outcomes = (
            status == base["result"]["status"] == "ok"
            and traced["result"]["arms"] == base["result"]["arms"]
        )
        data[tag] = report
        folders = sorted({p.split("/", 1)[0] for p in report["files"]})
        counts = {}
        for group in folders:
            subset = [lines for f, lines in report["files"].items() if f.startswith(group + "/")]
            counts[group] = dict(files=len(subset), lines=sum(map(len, subset)))
        summary[tag] = dict(
            exact_endpoint_and_rms=outcomes,
            status=status,
            paths=counts,
            evaluation_imports=report["forbidden_imports"],
            reported_frequency_objective=report["scores"].get(category),
            traced_timing=traced["resources"],
            untraced_timing=base["resources"],
            tracer_sha256=traced["tracer_sha256"],
        )
    if not data:
        return
    name = "trace-lines.json.gz"
    write(out / name, gzip.compress(json.dumps(data, sort_keys=True).encode(), mtime=0))
    save_json(
        out / "trace-summary.json",
        dict(
            id="DS29-0082",
            cpu=5,
            runs=summary,
            files={name: common.sha(out / name)},
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    args = p.parse_args()
    target = local_output(args.out)
    seal(args.work, target)
    score(target)
    trace_summary(args.work, target)


if __name__ == "__main__":
    main()
