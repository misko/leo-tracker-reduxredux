"""Seal and score paired guard decisions from one installed compact solve per roof offer."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distance_km
from ..variants.compact_tile_interior import margin
from . import measured_boundary_policy as trial
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

OFF, ON = "phase_release_guard_off", "phase_release_guard_20m"
BOUNDARY = "Recorded native GLRTs through installed compact solver and 20 m decision"
FIGURE_SHA = "9157ad289a85cc1475e926c28bb8836978d7dc9dc34817eb564d3561f4254cc8"
LABELS = {
    "near-inside": "Near inside",
    "near-outside": "Near omission",
    "six-outside": "6 km omitted",
}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile", "request_sha256")


def _number(text, scale=1):
    return int(text) / scale if text and text.isdecimal() else None


def resources(out, service, offer):
    marks = {
        name: whole_iq.read(out / (name + ".json"))
        for name in ("start", "solver-end", "end")
        if (out / (name + ".json")).exists()
    }
    state = service["state"]
    if any(state.get(key) != "0" for key in ("MainPID", "ControlPID")):
        raise ValueError("measured offer remained alive at scoring")
    if marks:
        group = marks["start"]["cgroup"]
        if Path(group).name != service["unit"] + ".service":
            raise ValueError("measured offer changed cgroup")
        events = Path("/sys/fs/cgroup") / group.lstrip("/") / "cgroup.events"
        if events.exists() and "populated 0" not in events.read_text().splitlines():
            raise ValueError("measured offer cgroup is still populated")
        for mark in marks.values():
            if (
                mark["cgroup"] != group
                or mark["cpus"] != [offer["cpu"]]
                or mark["memory.max"] != whole_iq.MEMORY
                or mark["memory.swap.max"] != 0
                or mark["memory.swap.current"] != 0
            ):
                raise ValueError("measured offer changed cores or resource limits")
    start, finish, end = (marks.get(k) for k in ("start", "solver-end", "end"))
    a, b = (
        _number(state.get(k), 1e6)
        for k in ("ActiveEnterTimestampMonotonic", "InactiveEnterTimestampMonotonic")
    )
    return dict(
        service=service,
        marks=marks,
        solver_wall_s=finish["monotonic_s"] - start["monotonic_s"] if finish else None,
        solver_cpu_s=(finish["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6
        if finish
        else None,
        cgroup_wall_s=end["monotonic_s"] - start["monotonic_s"]
        if end
        else (b - a if a and b else None),
        cgroup_cpu_s=(end["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6
        if end
        else _number(state.get("CPUUsageNSec"), 1e9),
        peak_bytes=end["memory.peak"] if end else _number(state.get("MemoryPeak")),
        guard_off_wall_s=end["guard_off_wall_s"] if end else None,
        guard_on_wall_s=end["guard_on_wall_s"] if end else None,
    )


def seal(work, report):
    path = whole_iq.checked(
        report / "source-lock.json", whole_iq.read(work / "launch-lock.json")["source_sha256"]
    )
    lock = whole_iq.read(path)
    for path, digest in lock["paths"].items():
        whole_iq.checked(Path(path), digest)
    install = Path(lock["install"])
    if (
        whole_iq.receiver_identity(install) != lock["installed_files"]
        or whole_iq.native_sources(install) != lock["native_sources"]
    ):
        raise ValueError("installed receiver differed from the frozen release")
    files = ["source-lock.json", "PROTOCOL.md", "positions.jsonl.gz", "resources.json"]
    rows, usage = [], {}
    for ident, offer in lock["offers"].items():
        out = work / ident
        whole_iq.checked(out / "request.json", offer["request_sha256"])
        service = whole_iq.read(out / "service.json")
        log = whole_iq.checked(out / "service.log", service["log_sha256"])
        usage[ident] = resource = resources(out, service, offer)
        state = service["state"]["Result"]
        if service["exit_code"] == 0 and state == "success" and "end" in resource["marks"]:
            original, decision = trial.check_pair(
                *[
                    (out / name).read_bytes()
                    for name in ("installed.json", "guard-off.json", "guard-on.json")
                ],
                offer["tile"],
            )
            resource["off_exact_byte_match"] = True
        else:
            status = "timed_out" if state == "timeout" else "failed"
            original = decision = dict(
                status=status,
                reason=state,
                boundary=BOUNDARY,
                metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            )
            resource["off_exact_byte_match"] = None
        for method, result in ((OFF, original), (ON, decision)):
            rows.append(
                dict(id=ident, method=method, result=result, **{k: offer[k] for k in MATCH})
            )
        for name in ("service.log", "installed.json", "guard-off.json", "guard-on.json"):
            file = out / name
            if file.exists():
                dest = f"{ident}-{name}"
                write(
                    report / dest, log.read_bytes() if name == "service.log" else file.read_bytes()
                )
                files.append(dest)
    pack(report / "positions.jsonl.gz", rows)
    save_json(report / "resources.json", usage)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=list(lock["offers"]),
            files={name: _sha(report / name) for name in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(rows, queries, usage):
    scores = []
    for row in rows:
        ident = row["id"]
        case = queries[ident]
        fit = row["result"]
        resource = usage[ident]
        true_margin = margin(case["truth"], row["tile"])
        containing = true_margin > 0
        if containing != (case["condition"] == "near-inside"):
            raise ValueError("archived roof condition and installed tile interior differ")
        for arm in ARMS:
            a = fit["arms"][arm]
            point, forced = a["latlon"], a.get("forced_latlon")
            evidence = point or forced
            scores.append(
                dict(
                    id=ident,
                    recording=case["recording"],
                    condition=case["condition"],
                    method=row["method"],
                    arm=arm,
                    status=fit["status"],
                    reason=fit.get("reason"),
                    published=point is not None,
                    false_publication=point is not None and not containing,
                    true_margin_km=true_margin,
                    fitted_margin_km=margin(evidence, row["tile"])
                    if evidence is not None
                    else None,
                    error_km=distance_km(point, case["truth"]),
                    forced_error_km=distance_km(forced, case["truth"]),
                    rms_hz=a.get("rf_rms_hz"),
                    solver_wall_s=resource["solver_wall_s"],
                    solver_cpu_s=resource["solver_cpu_s"],
                    cgroup_wall_s=resource["cgroup_wall_s"],
                    charged_peak_bytes=resource["peak_bytes"],
                    guard_cli_wall_s=resource["guard_on_wall_s"]
                    if row["method"] == ON
                    else resource["guard_off_wall_s"],
                )
            )
    return scores


def score(report):
    title = "20 m publication guard on six measured roof offers"
    lock = whole_iq.read(report / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(report / name, digest)
    source = trial.SOURCE / "archived-roof"
    archived = whole_iq.read(whole_iq.checked(source / "figure-lock.json", FIGURE_SHA))
    file = whole_iq.checked(
        source / "figure-queries.json", archived["files"]["figure-queries.json"]
    )
    queries = {q["id"]: q for q in whole_iq.read(file)["queries"] if q["id"] in lock["cases"]}
    rows = rows_from(report / "positions.jsonl.gz")
    if len(rows) != 2 * len(queries) or set(queries) != set(lock["cases"]):
        raise ValueError("the six paired offers require exactly two decisions")
    for row in rows:
        if any(row[key] != value for key, value in queries[row["id"]]["bindings"].items()):
            raise ValueError("sealed archived observation bindings differ from the numerical fit")
    scores = score_rows(rows, queries, whole_iq.read(report / "resources.json"))
    csv_file(report / "scores.csv", scores)
    by_id = {row["id"]: row for row in rows if row["method"] == OFF}
    queries_out = [
        dict(queries[ident], bindings={key: by_id[ident][key] for key in MATCH})
        for ident in lock["cases"]
    ]
    save_json(report / "figure-queries.json", dict(queries=queries_out))
    proof = ["source-lock.json", "prediction-lock.json", "resources.json", "scores.csv"]
    save_json(
        report / "figure-lock.json",
        dict(
            cases=lock["cases"],
            files={
                name: _sha(report / name)
                for name in ["positions.jsonl.gz", "figure-queries.json", *proof]
            },
        ),
    )
    chart = dict(
        id="measured-boundary-policy",
        method=ON,
        scope="transfer",
        title=title,
        caption=(
            "One installed compact fit per offer on two roof recordings. The 20 m rule "
            "can withhold both arms without changing their numerical endpoints."
        ),
        cases="sealed",
        seal="figure-lock.json",
        queries="figure-queries.json",
        condition_labels=LABELS,
        provenance=proof,
        series=[
            dict(
                key="candidate",
                label="20 m guard",
                forced_label="Endpoint at tile face",
                file="positions.jsonl.gz",
                value=ON,
            ),
            dict(
                key="stock",
                label="Guard off",
                file="positions.jsonl.gz",
                value=OFF,
                match=list(MATCH),
            ),
        ],
    )
    save_json(report / "figures.json", dict(version=1, charts=[chart]))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("seal", "score"))
    cli.add_argument("--work", type=local_output, default=trial.WORK)
    cli.add_argument("--out", type=local_output, default=trial.REPORT)
    args = cli.parse_args()
    if args.action == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)


if __name__ == "__main__":
    main()
