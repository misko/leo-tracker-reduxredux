"""Seal checksum-only receiver outcomes and render paired position and resource evidence."""

import argparse
import gzip
from pathlib import Path

import matplotlib

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import arm_execution_results as shared
from . import catalog_bench as trial
from . import screening_figures
from .full_v5_check import _sha
from .short_receiver_figures import _frozen_roof

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

METHODS = {"installed": "catalog_checksum_installed", "frozen_checksum": "catalog_checksum_frozen"}
LABELS = {"installed": "Installed checksum", "frozen_checksum": "Frozen ASCII checksum"}
STAGES = ("tracks", "initial_sky", "phase_history", "native_preparation")
BOUNDARY = "Complete stored original GLRT and causal TLEs through both compact v5 positions"


def receipt(work, source, ident, branch):
    folder = work / ident / branch
    row = source["cases"][ident]
    plan, service = (whole_iq.read(folder / n) for n in ("plan.json", "service.json"))
    if plan != dict(
        id=ident,
        branch=branch,
        cpus=[row["cpu"]],
        limit_s=source["cap_s"],
        source_sha256=_sha(work / "source-lock.json"),
    ):
        raise ValueError("position service plan differs from the paired registration")
    manager = service["systemd"]
    files = {
        n: _sha(folder / n)
        for n in ("plan.json", "service-launch.json", "service.json", "service.log")
    }
    if (
        manager["MainPID"] != "0"
        or service["binding"]["plan_sha256"] != files["plan.json"]
        or service["log_sha256"] != files["service.log"]
    ):
        raise ValueError("position service receipt is incomplete or differs from its own evidence")

    def metric(name, divisor):
        value = manager.get(name)
        return int(value) / divisor if str(value).isdigit() else None

    data = dict(
        id=ident,
        branch=branch,
        role=row["role"],
        cpu=row["cpu"],
        directory=str(folder),
        files=files,
        service_result=manager["Result"],
        service_cpu_s=metric("CPUUsageNSec", 1e9),
        service_wall_s=service["service_wall_s"],
        memory_peak_mib=metric("MemoryPeak", 2**20),
        cap_s=source["cap_s"],
    )
    for key in ("preparation", "numerical"):
        name = f"{key}.json"
        path = folder / name
        if path.is_file():
            files[name] = _sha(path)
            data[key] = whole_iq.read(path)
    if iq_service.succeeded(service):
        name = "worker-result.json"
        data |= whole_iq.read(folder / name)
        files[name] = _sha(folder / name)
        for key in ("start", "end"):
            mark = data[key]
            if (
                mark["cpus"] != [row["cpu"]]
                or mark["memory.max"] != source["memory_max"]
                or mark["memory.swap.max"] != source["swap_max"]
                or mark["memory.swap.current"] != 0
                or mark["memory.events.oom_kill"] != 0
                or mark["nice"] != 10
            ):
                raise ValueError("position service left its pinned CPU or 512 MiB memory contract")
        if not 0 < data["end"]["memory.peak"] <= source["memory_max"]:
            raise ValueError("position service exceeded its accounted memory cap")
        if (
            data["preparation"]["branch"] != branch
            or not 0 < data["preparation"]["checksum_calls"] <= data["numerical"]["checksum_calls"]
            or not 0 <= data["preparation"]["fallback_calls"] <= data["numerical"]["fallback_calls"]
        ):
            raise ValueError("position service failed to exercise the registered checksum")
    else:
        data["publication"] = dict(
            status="timed_out" if manager["Result"] == "timeout" else "failed",
            reason=manager["Result"],
            boundary=BOUNDARY,
            metrics={},
        )
    validate_result(data["publication"])
    return data


def science(result):
    return result | {"metrics": {k: v for k, v in result["metrics"].items() if k != "stage_s"}}


def parity(pair):
    stock, candidate = (pair[key] for key in METHODS)
    prepared = all("preparation" in leg for leg in pair.values())
    complete = all(leg["service_result"] == "success" for leg in pair.values())
    field_names = ("science", "provenance", "checksum_calls", "fallback_calls")
    proofs = (
        {name: stock["preparation"][name] == candidate["preparation"][name] for name in field_names}
        if prepared
        else {}
    )
    if complete:
        calibrated = set(ARMS)
        has_positions = all(
            set(leg["numerical"]["numerical"].get("arms", {})) == calibrated
            and all(
                fit.get("latlon") is not None
                for fit in leg["numerical"]["numerical"]["arms"].values()
            )
            for leg in pair.values()
        )
        full = science(stock["numerical"]["numerical"]) == science(
            candidate["numerical"]["numerical"]
        )
        output = science(stock["publication"]) == science(candidate["publication"])
        total_calls = all(
            stock["numerical"][key] == candidate["numerical"][key]
            for key in ("checksum_calls", "fallback_calls")
        )
    else:
        has_positions, full, output, total_calls = False, None, None, None
    return dict(
        prepared=prepared,
        complete=complete,
        genuine_positions=has_positions,
        matched_preparation=proofs,
        exact_numerical=full,
        exact_publication=output,
        exact_total_checksum_calls=total_calls,
        exact=all(proofs.values()) and full and output and total_calls if complete else None,
    )


def timing(data):
    prep = data.get("preparation", {})
    num = data.get("numerical", {})
    stages = num.get("numerical", {}).get("metrics", {}).get("stage_s", {})
    c = prep.get("clocks", {})
    causal = (c.get(stage, {}).get("cpu_s") for stage in ("initial_sky", "phase_history"))
    sky, phase = causal
    return {
        k: data[k]
        for k in (
            "id",
            "branch",
            "role",
            "cpu",
            "service_result",
            "service_cpu_s",
            "service_wall_s",
            "memory_peak_mib",
            "cap_s",
        )
    } | dict(
        status=data["publication"]["status"],
        worker_wall_s=data.get("worker_wall_s"),
        position_cpu_s=num.get("position_cpu_s"),
        position_wall_s=num.get("position_wall_s"),
        checksum_calls=num.get("checksum_calls"),
        fallback_calls=num.get("fallback_calls"),
        causal_preparation_cpu_s=sky + phase if sky is not None and phase is not None else None,
        **{
            f"{key}_{metric}": c.get(key, {}).get(metric)
            for key in STAGES
            for metric in (
                "cpu_s",
                "wall_s",
                "checksum_calls",
            )
        },
        **{
            f"{k}_wall_s": stages.get(k)
            for k in ("initial", "conservative", "family", "signed", "cavity")
        },
    )


def chart(report, cases, rows):
    by = {(r["id"], r["branch"]): r for r in rows}
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.15), sharey=True, layout="constrained")
    specs = (
        ("Causal catalogue + phase", "CPU seconds", ("causal_preparation_cpu_s",)),
        ("Full preparation", "CPU seconds", ("native_preparation_cpu_s",)),
        ("Full position service", "CPU seconds", ("service_cpu_s",)),
        ("Full position service", "Wall seconds", ("service_wall_s",)),
    )
    for axis, (title, unit, fields) in zip(axes, specs, strict=True):
        for index, (branch, color) in enumerate(zip(METHODS, ("#47617d", "#0b786b"), strict=True)):
            for j, ident in enumerate(cases):
                row = by[ident, branch]
                parts = [row[key] for key in fields]
                y = j + (index - 0.5) * 0.25
                if any(part is None for part in parts):
                    axis.text(0, y, "No result", va="center", fontsize=8)
                    continue
                bar = axis.barh(
                    y,
                    sum(parts),
                    height=0.22,
                    color=color,
                    label=LABELS[branch] if j == 0 else None,
                )
                if row["service_result"] != "success" and fields[0].startswith("service_"):
                    bar[0].set_hatch("///")
        axis.set_title(title)
        axis.set_xlabel(unit)
        axis.grid(axis="x", color="#dfe5ea")
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(
        range(len(cases)),
        [
            f"{ident} (shifted)" if by[ident, "installed"]["role"] == "shifted" else ident
            for ident in cases
        ],
    )
    axes[0].invert_yaxis()
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", frameon=False, ncols=2)
    for suffix in ("png", "pdf"):
        fig.savefig(report / f"stage.{suffix}", dpi=165)
    plt.close(fig)


def lock_files(report, name, paths, **extra):
    save_json(report / name, dict(extra, files={path: _sha(report / path) for path in paths}))


def score(report, positions):
    refs, _ = _frozen_roof()
    geography, frequency, queries = [], [], []
    for scope, rows in positions.items():
        for row in rows:
            ident, method = row["id"], row["method"]
            truth = refs[ident]["truth"]
            if scope == "shifted" and method == METHODS["installed"]:
                queries.append(
                    dict(
                        id=ident,
                        recording=ident,
                        condition="east-15-km",
                        truth=truth,
                        bindings={k: row[k] for k in shared.MATCH},
                    )
                )
            result = row["result"]
            for arm in ARMS:
                fit = result.get("arms", {}).get(arm, {})
                common = dict(
                    id=ident, method=method, scope=scope, arm=arm, status=result["status"]
                )
                geography.append(
                    dict(
                        common,
                        error_km=distance_km(fit.get("latlon"), truth),
                        forced_error_km=distance_km(fit.get("forced_latlon"), truth),
                    )
                )
                frequency.append(
                    dict(
                        common,
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    save_json(report / "shifted-queries.json", dict(queries=queries))
    shared.csv_file(report / "geography.csv", geography)
    shared.csv_file(report / "frequency.csv", frequency)


def figures(report, source, positions, output):
    charts = []
    for scope, rows in positions.items():
        shifted = scope == "shifted"
        position_file = output[scope]
        names = [
            "source-lock.json",
            "prediction-lock.json",
            "parity.json",
            "geography.csv",
            "frequency.csv",
        ]
        receipt_name = f"{scope}-figure-lock.json"
        lock_files(
            report,
            receipt_name,
            names + [position_file] + (["shifted-queries.json"] if shifted else []),
            cases=list(dict.fromkeys(r["id"] for r in rows)),
        )
        data = dict(
            id=f"catalog-checksum-{scope}",
            method=METHODS["frozen_checksum"],
            scope="transfer" if shifted else "roof",
            cases="sealed",
            seal=receipt_name,
            provenance=names,
            title="Frozen checksum on shifted offer"
            if shifted
            else "Frozen checksum on original offers",
            caption=(
                "The tile center is 15 km east. Both fits use the 20 m publication guard."
                if shifted
                else "Both compact v5 fits use the original GLRT and causal snapshots."
            ),
            series=[
                dict(
                    key="stock",
                    label=LABELS["installed"],
                    file=position_file,
                    value=METHODS["installed"],
                    match=shared.MATCH,
                ),
                dict(
                    key="candidate" if shifted else "one",
                    label=LABELS["frozen_checksum"],
                    file=position_file,
                    value=METHODS["frozen_checksum"],
                ),
            ],
        )
        if shifted:
            data.update(
                queries="shifted-queries.json", condition_labels={"east-15-km": "15 km east"}
            )
            data["series"][0]["forced_label"] = "Installed diagnostic"
            data["series"][1]["forced_label"] = "Frozen checksum diagnostic"
        charts.append(data)
    save_json(report / "figures.json", dict(version=2, charts=charts))
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="catalog-checksum-timing",
            title="Checksum-only preparation and position service",
            sample=f"{len(source['cases'])} original recordings, two services per recording",
            boundary=BOUNDARY,
            note="Pairs share one CPU and a 180 s limit. Hatching shows incomplete services.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    lock_files(
        report,
        "stage-figure-lock.json",
        (
            "stage.png",
            "stage.pdf",
            "stage.csv",
            "stage-figure.json",
            "prediction-lock.json",
        ),
    )
    screening_figures.generate(report / "charts", evidence=report)


def publish(work, report, audit_path):
    source_path = whole_iq.checked(work / "source-lock.json", _sha(report / "source-lock.json"))
    source = whole_iq.read(source_path)
    audit = whole_iq.read(audit_path)
    if audit["source_lock_sha256"] != _sha(source_path) or set(audit["catalogues"]) != set(
        source["cases"]
    ):
        raise ValueError("the strict catalogue audit differs from the sealed position study")
    write(report / "catalogue-audit.json", audit_path.read_bytes())
    measured, exact, times = {}, {}, []
    positions = {"original": [], "shifted": []}
    for ident in source["sequence"]:
        row = source["cases"][ident]
        pair = {branch: receipt(work, source, ident, branch) for branch in METHODS}
        measured[ident], exact[ident] = pair, parity(pair)
        for branch, data in pair.items():
            times.append(timing(data))
            positions[row["role"]].append(
                dict(
                    id=ident,
                    recording=ident,
                    method=METHODS[branch],
                    attempted=True,
                    result=data["publication"],
                    **shared.bindings(row),
                )
            )
    output = {scope: f"{scope}-positions.jsonl.gz" for scope in positions}
    for scope, rows in positions.items():
        write(
            report / output[scope],
            gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0),
        )
    save_json(report / "resources.json", measured)
    save_json(report / "parity.json", exact)
    shared.csv_file(report / "stage.csv", times)
    lock_files(
        report,
        "prediction-lock.json",
        (
            "source-lock.json",
            "resources.json",
            "parity.json",
            "stage.csv",
            "catalogue-audit.json",
            *output.values(),
        ),
        cases=source["sequence"],
    )
    score(report, positions)
    chart(report, source["sequence"], times)
    figures(report, source, positions, output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("audit", type=Path)
    args = parser.parse_args()
    publish(args.work, trial.REPORT, args.audit)
