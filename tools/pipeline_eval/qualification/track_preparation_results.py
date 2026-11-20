"""Verify and render exact track-preparation measured comparisons."""

import argparse
import gzip

import matplotlib

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import distance_km, validate_result
from . import arm_execution_results as shared
from . import screening_figures
from . import track_preparation_trial as trial
from .full_v5_check import _sha
from .short_receiver_figures import _frozen_roof

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

METHODS = {"installed": "track_preparation_original", "shared": "track_preparation_shared"}
COMPLETION = "track_preparation_installed_completion_check"
SCIENCE = (
    "ordered_tracks_sha256",
    "causal_sha256",
    "observations",
    "tracks",
    "assigned_points",
    "curved_tracks",
    "checksums",
    "polynomial_choices",
    "rejected_choices",
)
BOUNDARY = "Complete original GLRT and causal TLEs through the paired compact decision"


def read_leg(work, ident, row, mode):
    folder = work / ident / mode
    plan, receipt = [whole_iq.read(folder / name) for name in ("plan.json", "service.json")]
    if plan != dict(
        id=ident,
        mode=mode,
        cpus=[row["cpu"]],
        limit_s=trial.CAP,
        source_sha256=_sha(work / "source-lock.json"),
    ):
        raise ValueError("service differs from the matched complete input plan")
    systemd = receipt["systemd"]
    if systemd["MainPID"] != "0":
        raise ValueError("position service is not reconciled")
    status = systemd["Result"]
    cpu, peak = systemd.get("CPUUsageNSec"), systemd.get("MemoryPeak")
    files = {n: _sha(folder / n) for n in ("plan.json", "service.json", "service.log")}
    result = dict(
        directory=str(folder),
        files=files,
        wall_s=receipt["service_wall_s"],
        cpu_s=int(cpu) / 1e9 if str(cpu).isdigit() else None,
        peak_mib=int(peak) / 2**20 if str(peak).isdigit() else None,
        service_result=status,
        backend=mode,
    )
    if not iq_service.succeeded(receipt):
        return dict(
            result,
            publication=dict(
                status="timed_out" if status == "timeout" else "failed",
                reason=status,
                boundary=BOUNDARY,
                metrics={},
            ),
        )
    measured = whole_iq.read(folder / "worker-result.json")
    files["worker-result.json"] = _sha(folder / "worker-result.json")
    for key in ("start", "end"):
        mark = measured[key]
        if (
            mark["cpus"] != [row["cpu"]]
            or mark["memory.max"] != whole_iq.MEMORY
            or mark["memory.swap.max"] != 0
            or mark["memory.swap.current"] != 0
            or mark["memory.events.oom_kill"] != 0
        ):
            raise ValueError("complete position worker exceeded its registered resource scope")
    validate_result(measured["publication"])
    return result | measured | {"peak_mib": measured["end"]["memory.peak"] / 2**20}


def compare(controls):
    stock, new = (controls[k] for k in METHODS)
    if "preparation" not in stock or "preparation" not in new:
        return dict(complete=False, exact=None)
    same = {key: stock["preparation"].get(key) == new["preparation"].get(key) for key in SCIENCE}
    science = shared.science(stock["publication"]) == shared.science(new["publication"])
    return dict(
        complete=True,
        exact=all(same.values()) and science,
        preparation_equal=same,
        full_decision_equal=science,
    )


def fields(ident, role, cpu, row):
    stage = row.get("preparation", {}).get("clocks", {})

    def time(key, clock):
        return stage.get(key, {}).get(clock + "_s")

    return dict(
        id=ident,
        mode=row["backend"],
        role=role,
        cpu=cpu,
        terminal_status=row["publication"]["status"],
        service_result=row["service_result"],
        service_cpu_s=row["cpu_s"],
        service_wall_s=row["wall_s"],
        peak_mib=row["peak_mib"],
        **{
            f"{key}_{clock}_s": time(key, clock)
            for key in (
                "tracks",
                "polynomial_choice",
                "initial_sky",
                "phase_history",
                "native_preparation",
            )
            for clock in ("cpu", "wall")
        },
        **{
            key: row.get("preparation", {}).get(key)
            for key in (
                "observations",
                "tracks",
                "assigned_points",
                "curved_tracks",
                "checksums",
                "fallback_checksums",
                "rejected_choices",
            )
        },
    )


def chart(report, rows):
    cases = list(dict.fromkeys(r["id"] for r in rows))
    by = {(r["id"], r["mode"]): r for r in rows}
    fig, axes = plt.subplots(ncols=3, figsize=(12, 4.6), sharey=True, layout="constrained")
    configs = (
        ("Track preparation", ("tracks_cpu_s",)),
        ("Causal catalogue and phase", ("initial_sky_cpu_s", "phase_history_cpu_s")),
        ("Complete position service", ("service_cpu_s",)),
    )
    for axis, (title, columns) in zip(axes, configs, strict=True):
        for idx, (mode, color, label) in enumerate(
            zip(
                METHODS,
                ("#405a77", "#087a70"),
                ("Installed preparation", "Shared support and bytewise checksums"),
                strict=True,
            )
        ):
            for j, ident in enumerate(cases):
                row = by[ident, mode]
                parts = [row[k] for k in columns]
                if any(p is None for p in parts):
                    continue
                axis.barh(
                    j + (idx - 0.5) * 0.24,
                    sum(parts),
                    height=0.21,
                    color=color,
                    label=label if j == 0 else None,
                )
        axis.set_title(title)
        axis.set_xlabel("CPU-seconds")
        axis.set_yticks(range(len(cases)), cases)
        axis.grid(axis="x", color="#dee4ea")
        axis.set_axisbelow(True)
    axes[0].invert_yaxis()
    handles, labels = axes[-1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncols=2, frameon=False)
    fig.suptitle("Exact preparation on complete stored GLRT and causal catalogues")
    for ext in ("png", "pdf"):
        fig.savefig(report / f"stage.{ext}", dpi=160)
    plt.close(fig)


def seal(report, name, files, **extra):
    save_json(report / name, dict(extra, files={n: _sha(report / n) for n in files}))


def publish(work, report, completion=None):
    path = whole_iq.checked(work / "source-lock.json", _sha(report / "source-lock.json"))
    source = whole_iq.read(path)
    audit, results, timing = {}, {}, []
    positions = {"roof": [], "shifted": []}
    for ident, row in source["cases"].items():
        legs = {mode: read_leg(work, ident, row, mode) for mode in METHODS}
        results[ident] = legs
        audit[ident] = compare(legs)
        label = "shifted" if row["role"] == "shifted" else "roof"
        for mode, data in legs.items():
            positions[label].append(
                dict(
                    id=ident,
                    method=METHODS[mode],
                    result=data["publication"],
                    attempted=True,
                    **shared.bindings(row),
                )
            )
            timing.append(fields(ident, row["role"], row["cpu"], data))
    extra = []
    if completion is not None:
        lock = whole_iq.read(report / "completion-check-lock.json")
        ident = lock["id"]
        row = source["cases"][ident]
        whole_iq.checked(completion / "source-lock.json", lock["original_source_sha256"])
        whole_iq.checked(work / ident / "installed/service.json", lock["primary_service_sha256"])
        if results[ident]["installed"]["service_result"] != "timeout" or row["role"] != "shifted":
            raise ValueError("completion check must keep the primary shifted timeout")
        terminal = read_leg(completion, ident, row, "installed")
        followup = compare(results[ident] | {"installed": terminal})
        save_json(report / "completion-check.json", dict(result=terminal, audit=followup))
        audit[ident]["completion_check"] = followup
        positions["shifted"].append(
            dict(
                id=ident,
                method=COMPLETION,
                result=terminal["publication"],
                attempted=True,
                **shared.bindings(row),
            )
        )
        extra.extend(("completion-check-lock.json", "completion-check.json"))
    output = {name: f"{name}-positions.jsonl.gz" for name in positions}
    for label, rows in positions.items():
        write(
            report / output[label],
            gzip.compress(b"".join(encoded(x) + b"\n" for x in rows), mtime=0),
        )
    save_json(report / "parity.json", audit)
    save_json(report / "resources.json", results)
    shared.csv_file(report / "stage.csv", timing)
    provenance = (
        "source-lock.json",
        "resources.json",
        "parity.json",
        "stage.csv",
        *output.values(),
        *extra,
        *(f"profile-{ident}.json" for ident in trial.track_preparation_profile.PILOTS),
    )
    seal(report, "prediction-lock.json", provenance, cases=list(source["cases"]))
    chart(report, timing)
    figures(report, source, positions, output, extra)


def figures(report, source, positions, output, extra):
    refs, _ = _frozen_roof()
    prior = whole_iq.read(trial.PRIOR_EDGE / "figure-lock.json")["files"]
    query = whole_iq.checked(trial.PRIOR_EDGE / "figure-queries.json", prior["figure-queries.json"])
    (original,) = (
        row for row in whole_iq.read(query)["queries"] if row["id"] == source["edge_query"]
    )
    edge = original["recording"]
    edge_row = source["cases"][edge]
    if original["bindings"]["tile"] != edge_row["spec"]["tile"]:
        raise ValueError("shifted truth does not match the prospective offer")
    save_json(
        report / "shifted-queries.json",
        dict(
            queries=[
                dict(
                    id=edge,
                    recording=edge,
                    condition="near-outside",
                    truth=original["truth"],
                    bindings=shared.bindings(edge_row),
                )
            ]
        ),
    )
    scores = []
    for label, rows in positions.items():
        for r in rows:
            id_ = r["id"]
            truth = original["truth"] if id_ == edge else refs[id_]["truth"]
            for arm in ("c0", "fitted_c"):
                result = r["result"]
                fit = result.get("arms", {}).get(arm, {})
                scores.append(
                    dict(
                        id=id_,
                        method=r["method"],
                        scope=label,
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(fit.get("latlon"), truth),
                        forced_error_km=distance_km(fit.get("forced_latlon"), truth),
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    shared.csv_file(report / "scores.csv", scores)
    charts = []
    for label, rows in positions.items():
        file = output[label]
        shifted = label == "shifted"
        support = ["source-lock.json", "prediction-lock.json", "parity.json", "scores.csv"]
        if shifted:
            support.extend(extra)
        files = [*support, file] + (["shifted-queries.json"] if shifted else [])
        receipt = f"{label}-figure-lock.json"
        seal(report, receipt, files, cases=list(dict.fromkeys(r["id"] for r in rows)))
        chart = dict(
            id=f"track-preparation-{label}",
            method=METHODS["shared"],
            scope="transfer" if shifted else "roof",
            title="Exact track preparation on the original paired position inputs",
            caption="Stored original GLRT and causal orbit inputs are matched across both methods.",
            cases="sealed",
            seal=receipt,
            provenance=support,
            series=[
                dict(
                    key="stock",
                    label="Installed preparation",
                    file=file,
                    value=METHODS["installed"],
                    match=shared.MATCH,
                ),
                dict(
                    key="candidate" if shifted else "one",
                    label="Shared preparation",
                    file=file,
                    value=METHODS["shared"],
                ),
            ],
        )
        if shifted:
            chart.update(
                queries="shifted-queries.json", condition_labels={"near-outside": "Near omission"}
            )
            chart["series"][1]["forced_label"] = "Withheld diagnostic"
            if extra:
                chart["series"].append(
                    dict(
                        key="four",
                        label="Installed completion check",
                        file=file,
                        value=COMPLETION,
                        match=shared.MATCH,
                        forced_label="Completion check diagnostic",
                    )
                )
        charts.append(chart)
    save_json(report / "figures.json", dict(version=2, charts=charts))
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="track-preparation-timing",
            title="Exact preparation timing",
            sample="Four complete stored native recordings, two measured services per recording",
            boundary="Original GLRT and causal orbits through both compact calibration arms",
            note="One pinned CPU per service. Stage CPU includes matched instrumentation.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    seal(
        report,
        "stage-figure-lock.json",
        ("stage.png", "stage.pdf", "stage.csv", "stage-figure.json", "prediction-lock.json"),
    )
    screening_figures.generate(report / "charts", evidence=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--completion", type=local_output)
    option = parser.parse_args()
    publish(option.work, trial.REPORT, option.completion)
