"""Verify and publish the paired policy, independent selected arms and resources."""

import argparse
import csv
import gzip
from hashlib import sha256
from io import StringIO

import matplotlib

from .. import iq_service, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import distance_km, validate_result
from ..variants import arm_execution
from . import arm_execution_trial as trial
from . import screening_figures
from .full_v5_check import _sha

matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402

CONTROL = "arm_execution_paired_control"
SELECTED = "arm_execution_independent_selection"
MODES = ("control", "c0", "fitted_c")
MATCH = ("native_sha256", "catalog_sha256", "input_sha256", "tile", "original_request_sha256")


def csv_file(path, rows):
    buffer = StringIO(newline="")
    values = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\n")
    values.writeheader()
    values.writerows(rows)
    write(path, buffer.getvalue().encode())


def leg(work, ident, mode, row):
    folder = work / ident / mode
    plan, service = [whole_iq.read(folder / name) for name in ("plan.json", "service.json")]
    if plan != dict(
        id=ident,
        mode=mode,
        cpus=[row["cpu"]],
        limit_s=trial.CAP,
        source_sha256=_sha(work / "source-lock.json"),
    ):
        raise ValueError(f"unmatched {ident}/{mode} measurement")
    files = {name: _sha(folder / name) for name in ("plan.json", "service.json", "service.log")}
    manager = service["systemd"]
    if manager["MainPID"] != "0":
        raise ValueError("position worker did not reconcile terminal service")
    resources = dict(
        service_cpu_s=int(manager["CPUUsageNSec"]) / 1e9
        if str(manager.get("CPUUsageNSec")).isdigit()
        else None,
        service_wall_s=service["service_wall_s"],
        memory_peak_bytes=int(manager["MemoryPeak"])
        if str(manager.get("MemoryPeak")).isdigit()
        else None,
        service_result=manager["Result"],
        worker_wall_s=None,
    )
    if not iq_service.succeeded(service):
        status = "timed_out" if manager["Result"] == "timeout" else "failed"
        failure = dict(
            status=status,
            boundary="Complete native paired receiver service",
            reason=manager["Result"],
            metrics={},
        )
        return dict(publication=failure, resources=resources, files=files, directory=str(folder))
    measured = whole_iq.read(folder / "worker-result.json")
    files["worker-result.json"] = _sha(folder / "worker-result.json")
    before, after = measured["start"], measured["end"]
    for edge in (before, after):
        if (
            edge["cpus"] != [row["cpu"]]
            or edge["memory.max"] != whole_iq.MEMORY
            or edge["memory.swap.max"] != 0
            or edge["memory.swap.current"] != 0
            or edge["memory.events.oom_kill"] != 0
        ):
            raise ValueError("worker caps or affinity changed")
    resources.update(
        worker_wall_s=measured["worker_wall_s"],
        worker_cpu_s=(after["cpu.stat.usage_usec"] - before["cpu.stat.usage_usec"]) / 1e6,
        memory_peak_bytes=after["memory.peak"],
    )
    return dict(measured, files=files, directory=str(folder), resources=resources)


def science(result):
    """Projection count and measured clocks are separate from numerical evidence."""
    return dict(
        result,
        metrics={
            k: v
            for k, v in result["metrics"].items()
            if k not in ("stage_s", "compact_projections")
        },
    )


def compare(cases, tile, policy):
    control = cases["control"]["publication"]
    if any("numerical" not in row for row in cases.values()):
        return dict(
            status="failed",
            reason="incomplete_independent_arm_pair",
            metrics={},
            boundary=control["boundary"],
        ), dict(complete=False, exact=None)
    stock = cases["control"]["numerical"]
    expected = {
        name: arm_execution.selected(stock, name, tile, policy) for name in arm_execution.ARMS
    }
    actual = {name: cases[name]["selected"] for name in arm_execution.ARMS}
    if actual["c0"]["paired_decision_sha256"] != actual["fitted_c"]["paired_decision_sha256"]:
        raise ValueError("independent executions disagreed on the paired scientific decision")
    template = cases["c0"]["publication"]
    metrics = dict(template["metrics"])
    for name, chosen in actual.items():
        if chosen["frequency_score"] is not None:
            metrics[f"{name}_frequency_score"] = chosen["frequency_score"]
    result = dict(
        template, arms={name: chosen["fit"] for name, chosen in actual.items()}, metrics=metrics
    )
    validate_result(result)
    exact = dict(
        complete=True,
        exact=actual == expected
        and all(science(row["numerical"]) == science(stock) for row in cases.values()),
        arm_equal={k: actual[k] == expected[k] for k in actual},
        paired_decision_sha256=actual["c0"]["paired_decision_sha256"],
    )
    return result, exact


def chart(report, ids, measured):
    fig, ax = plt.subplots(ncols=2, figsize=(10, 4), sharey=True, layout="constrained")
    colors = ("#445e79", "#177f73", "#b65c32")
    labels = ("Original pair", "Selected c = 0", "Selected fitted c")
    for axis, field, title in zip(
        ax,
        ("service_cpu_s", "service_wall_s"),
        ("Cgroup process CPU", "Service elapsed wall"),
        strict=True,
    ):
        for idx, (mode, color, label) in enumerate(zip(MODES, colors, labels, strict=True)):
            for index, ident in enumerate(ids):
                value = measured[ident][mode]["resources"][field]
                if value is not None:
                    axis.barh(
                        index + (idx - 1) * 0.22,
                        value,
                        height=0.19,
                        color=color,
                        label=label if index == 0 else None,
                    )
        axis.set_yticks(range(len(ids)), ids)
        axis.set_xlabel("Seconds")
        axis.set_title(title)
        axis.grid(axis="x", color="#dee4ea")
        axis.set_axisbelow(True)
    ax[0].invert_yaxis()
    handles, entries = ax[1].get_legend_handles_labels()
    fig.legend(handles, entries, loc="outside lower center", ncols=3, frameon=False)
    fig.suptitle("Compact paired inference with one requested publication")
    for suffix in ("png", "pdf"):
        fig.savefig(report / f"stage.{suffix}", dpi=160)
    plt.close(fig)


def bindings(row):
    spec = row["spec"]
    return {k: spec[k] for k in MATCH if k != "input_sha256"} | {
        "input_sha256": sha256(encoded(trial.compact(spec))).hexdigest(),
    }


def publish(first, ordinary, report):
    original_path = whole_iq.checked(first / "source-lock.json", _sha(report / "source-lock.json"))
    correction_path = whole_iq.checked(
        ordinary / "source-lock.json", _sha(report / "ordinary-execution-lock.json")
    )
    original, corrected = map(whole_iq.read, (original_path, correction_path))
    if corrected["prior_source_sha256"] != _sha(original_path):
        raise ValueError("ordinary width normalization does not bind the original lock")
    row_cases = {**original["cases"], **corrected["cases"]}
    output, edge_output, measured, timing, audits = [], [], {}, [], {}
    incident = []
    for ident, row in row_cases.items():
        edge = row["role"] == "established-edge"
        work = first if edge else ordinary
        if not edge:
            old = original["cases"][ident]
            old_spec = old["spec"]
            if row != old | {"spec": old_spec | {"tile": old_spec["tile"] | {"width_km": 25.0}}}:
                raise ValueError(
                    "ordinary retries changed more than the registered default width field"
                )
            for mode in MODES:
                setup = first / ident / mode
                service = whole_iq.read(setup / "service.json")
                if iq_service.succeeded(service) or (setup / "worker-result.json").exists():
                    raise ValueError("duplicate completed original ordinary service")
                incident.append(
                    dict(
                        id=ident,
                        mode=mode,
                        directory=str(setup),
                        service_sha256=_sha(setup / "service.json"),
                        log_sha256=_sha(setup / "service.log"),
                        result=service["systemd"]["Result"],
                    )
                )
        measured[ident] = {mode: leg(work, ident, mode, row) for mode in MODES}
        actual = measured[ident]
        candidate, audits[ident] = compare(actual, row["spec"]["tile"], row["publication"])
        target = edge_output if edge else output
        for method, result in ((CONTROL, actual["control"]["publication"]), (SELECTED, candidate)):
            target.append(
                dict(
                    id=ident,
                    recording=ident,
                    method=method,
                    result=result,
                    attempted=True,
                    **bindings(row),
                )
            )
        for mode, data in actual.items():
            stages = data.get("numerical", {}).get("metrics", {}).get("stage_s", {})
            stats = data.get("phase_views", {})
            info = data.get("trace", {}).get("conservative", {})
            res = data["resources"]
            timing.append(
                dict(
                    id=ident,
                    mode=mode,
                    cohort=row["role"],
                    cpu=row["cpu"],
                    cap_s=trial.CAP,
                    result=data["publication"]["status"],
                    service_result=res["service_result"],
                    cpu_s=res["service_cpu_s"],
                    wall_s=res["service_wall_s"],
                    worker_wall_s=res["worker_wall_s"],
                    peak_cgroup_mib=res["memory_peak_bytes"] / 2**20
                    if res["memory_peak_bytes"] is not None
                    else None,
                    conservative_s=stages.get("conservative"),
                    paired_initial_s=stages.get("initial"),
                    family_s=stages.get("family"),
                    signed_s=stages.get("signed"),
                    cavity_s=stages.get("cavity"),
                    phase_views_calls=stats.get("calls"),
                    phase_views_reused=stats.get("reused"),
                    unused_association_reports_avoided=len(info.get("returned_arms", []))
                    if mode != "control"
                    else 0,
                )
            )
    save_json(report / "resources.json", measured)
    save_json(report / "setup-attempts.json", incident)
    save_json(report / "parity.json", audits)
    csv_file(report / "stage.csv", timing)
    for name, rows in (("positions.jsonl.gz", output), ("edge-positions.jsonl.gz", edge_output)):
        write(report / name, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))
    base_files = (
        "source-lock.json",
        "ordinary-execution-lock.json",
        "resources.json",
        "parity.json",
        "positions.jsonl.gz",
        "edge-positions.jsonl.gz",
        "stage.csv",
        "setup-attempts.json",
    )
    save_json(
        report / "prediction-lock.json",
        dict(cases=list(row_cases), files={f: _sha(report / f) for f in base_files}),
    )
    chart(report, row_cases, measured)
    publish_scores(report, output, edge_output, row_cases)


def publish_scores(report, roof, edge, cases):
    from .short_receiver_figures import _frozen_roof

    refs, _ = _frozen_roof()
    old_file = (
        trial.sequential_fix_trial.SCREEN
        / "receiver-core/measured-boundary-policy/figure-queries.json"
    )
    authority = whole_iq.read(old_file.with_name("figure-lock.json"))["files"]
    query_source = whole_iq.checked(old_file, authority[old_file.name])
    input_source = old_file.with_name("source-lock.json")
    whole_iq.checked(input_source, authority[input_source.name])
    old_query = next(r for r in whole_iq.read(query_source)["queries"] if r["id"] == trial.EDGE)
    ident = old_query["recording"]
    if any(
        old_query["bindings"][key] != cases[ident]["spec"][key]
        for key in ("native_sha256", "catalog_sha256", "tile")
    ):
        raise ValueError("historical edge truth differs from the replayed offer")
    save_json(
        report / "edge-queries.json",
        dict(
            queries=[
                dict(
                    id=ident,
                    recording=ident,
                    truth=old_query["truth"],
                    condition="near-inside",
                    bindings=bindings(cases[ident]),
                )
            ]
        ),
    )
    scores = []
    for row in [*roof, *edge]:
        ident = row["id"]
        truth = old_query["truth"] if ident == old_query["recording"] else refs[ident]["truth"]
        result = row["result"]
        for name in arm_execution.ARMS:
            arm = result.get("arms", {}).get(name, {})
            scores.append(
                dict(
                    id=ident,
                    method=row["method"],
                    calibration=name,
                    status=result["status"],
                    geographic_error_km=distance_km(arm.get("latlon"), truth),
                    forced_error_km=distance_km(arm.get("forced_latlon"), truth),
                    rf_rms_hz=arm.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{name}_frequency_score"),
                )
            )
    csv_file(report / "scores.csv", scores)
    for records, condition, name in (
        (roof, "roof", "positions.jsonl.gz"),
        (edge, "edge", "edge-positions.jsonl.gz"),
    ):
        files = [name, "source-lock.json", "prediction-lock.json", "parity.json", "scores.csv"]
        if condition == "edge":
            files.append("edge-queries.json")
        save_json(
            report / f"{condition}-figure-lock.json",
            dict(
                cases=list(dict.fromkeys(r["id"] for r in records)),
                files={n: _sha(report / n) for n in files},
            ),
        )
    charts = []
    for edge_case in (False, True):
        condition = "edge" if edge_case else "roof"
        file = "edge-positions.jsonl.gz" if edge_case else "positions.jsonl.gz"
        series = [
            dict(
                file=file, key="stock", value=CONTROL, label="Installed paired control", match=MATCH
            ),
            dict(
                file=file,
                key="candidate" if edge_case else "one",
                value=SELECTED,
                label="Independently selected arms",
            ),
        ]
        descriptor = dict(
            id=f"arm-execution-{condition}",
            method=SELECTED,
            scope="transfer" if edge_case else "roof",
            title="Paired guard on the shifted archived offer"
            if edge_case
            else "Compact position from one requested calibration",
            caption="Selected executions use the paired decision and return the requested fit.",
            cases="sealed",
            seal=f"{condition}-figure-lock.json",
            series=series,
            provenance=["source-lock.json", "prediction-lock.json", "parity.json", "scores.csv"],
        )
        if edge_case:
            descriptor.update(
                queries="edge-queries.json",
                condition_labels={"near-inside": "Near inside, known guard edge"},
            )
            series[-1]["forced_label"] = "Candidate, withheld endpoint"
        charts.append(descriptor)
    save_json(report / "figures.json", dict(version=2, charts=charts))
    save_json(
        report / "stage-figure.json",
        dict(
            version=1,
            id="arm-execution-timing",
            title="Compact calibration execution time",
            sample="Four complete native captures with three measured services per offer",
            boundary="Cgroup service from authenticated GLRT factors through paired publication",
            note="Selected outputs retain paired gates and both numerical fits.",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
            seal="stage-figure-lock.json",
        ),
    )
    files = (
        "stage.png",
        "stage.pdf",
        "stage.csv",
        "stage-figure.json",
        "prediction-lock.json",
        "resources.json",
    )
    save_json(report / "stage-figure-lock.json", dict(files={n: _sha(report / n) for n in files}))
    screening_figures.generate(report / "charts", evidence=report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("edge", type=local_output)
    parser.add_argument("ordinary", type=local_output)
    args = parser.parse_args()
    publish(args.edge, args.ordinary, trial.REPORT)
