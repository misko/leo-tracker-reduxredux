"""Close the standalone pair receipts, then score the frozen positions."""

import argparse
import gzip
from difflib import unified_diff
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import compact_cut_trial as trial
from .cavity_payload import packed
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

FILES = {trial.STOCK: "stock-positions.jsonl.gz", trial.CANDIDATE: "positions.jsonl.gz"}
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")


def verified_attempt(work, plan, ident, method):
    run = work / ident / method
    row = whole_iq.read(run / "attempt.json")
    want = dict(
        id=ident,
        cpu=plan["cpus"][ident],
        method=method,
        order=plan["orders"][ident].index(method),
        native_sha256=plan["bindings"][ident]["native_sha256"],
        plan_sha256=_sha(work / "plan.json"),
    )
    if {key: row[key] for key in want} != want:
        raise ValueError("completed attempt has the wrong source, input, CPU, or method order")
    whole_iq.checked(run / "position.json", row["result_sha256"])
    whole_iq.checked(run / "service.log", row["service_log_sha256"])
    validate_result(row["result"])
    evidence = row["measures"]
    if row["service_status"] == "success" and (
        row["result"] != whole_iq.read(run / "position.json")
        or row["returncode"] != 0
        or set(evidence) != {"ready", "finish", "imports", "decisions"}
    ):
        raise ValueError("successful output requires complete matching worker evidence")
    for edge in ("ready", "finish"):
        if edge in evidence:
            cap = evidence[edge]
            if (
                cap["memory.max"] != plan["cap_bytes"]
                or cap["memory.swap.max"] != plan["swap_bytes"]
                or cap["memory.swap.current"]
                or cap["memory.peak"] > plan["cap_bytes"]
            ):
                raise ValueError("observed receiver memory policy differs from the plan")
    if "ready" in evidence and (evidence["ready"]["cpu"], evidence["ready"]["nice"]) != (
        row["cpu"],
        10,
    ):
        raise ValueError("worker ran outside its assigned CPU or priority")
    return row


def parity(stock, candidate):
    a, b = (row["result"] for row in (stock, candidate))
    paired_fix = a["status"] == b["status"] == "ok"
    arm_equal = {arm: a["arms"][arm] == b["arms"][arm] for arm in ARMS} if paired_fix else {}

    def science(result):
        return {key: value for key, value in result["metrics"].items() if key != "stage_s"}

    old, new = (row["measures"].get("decisions", {}) for row in (stock, candidate))
    decisions = {
        name: name in old and name in new and old[name] == new[name]
        for name in old.keys() | new.keys()
    }
    if any(result["metrics"].get("cavity_offered") for result in (a, b)):
        decisions.setdefault("cavity", False)
    return dict(
        stock_status=a["status"],
        candidate_status=b["status"],
        identical_arms=arm_equal,
        identical_publication=a["status"] == b["status"],
        identical_counters_and_scores=science(a) == science(b) if paired_fix else None,
        identical_decisions=decisions,
        stock_cavity_trials=len(old.get("cavity", {}).get("replacements", [])),
        candidate_cavity_trials=len(new.get("cavity", {}).get("replacements", [])),
        stock_cavity_adopted=old.get("cavity", {}).get("accepted"),
        candidate_cavity_adopted=new.get("cavity", {}).get("accepted"),
    )


def resources(row):
    end = row["measures"].get("finish", {})
    terminal_peak = row["kernel"]["MemoryPeak"]
    imports = row["measures"].get("imports", {})
    return dict(
        id=row["id"],
        method=row["method"],
        cpu=row["cpu"],
        order=row["order"],
        result=row["result"]["status"],
        service=row["service_status"],
        wall_s=row["wall_s"],
        receiver_wall_s=end.get("wall_s"),
        process_cpu_s=end.get("cpu_s"),
        charged_peak_bytes=end.get(
            "memory.peak", int(terminal_peak) if terminal_peak.isdecimal() else None
        ),
        process_rss_peak_kib=end.get("rss_peak_kib"),
        project_imports=len(imports["project"]) if imports else None,
        external_import_roots=len(imports["third_party"]) if imports else None,
        stdlib_import_roots=len(imports["standard_library"]) if imports else None,
        **{
            f"{key}_wall_s": value
            for key, value in row["result"]["metrics"].get("stage_s", {}).items()
        },
    )


def measure_source(plan, out, *, publish):
    a, b = (plan["builds"][method] for method in FILES)
    a_root, b_root = Path(a["root"]), Path(b["root"])
    changed = [n for n, h in a["files"].items() if n.endswith(".py") and b["files"][n] != h]
    diff = []
    for name in changed:
        old, new = (
            (root / name).read_text().splitlines(keepends=True) for root in (a_root, b_root)
        )
        diff.extend(unified_diff(old, new, fromfile=f"a/{name}", tofile=f"b/{name}"))
    write(out / "installed-change.patch", "".join(diff).encode())
    names = ["installed-change.patch"]
    if publish:
        digests = {
            n: h
            for n, h in (b["files"] | b["compiler_sources"]).items()
            if n.endswith((".py", ".c"))
        }
        files = {n: whole_iq.checked(b_root / n, h).read_bytes() for n, h in digests.items()}
        write(out / "receiver-source.tar.gz", packed(files))
        save_json(
            out / "package.json",
            dict(
                files=digests,
                archive_sha256=_sha(out / "receiver-source.tar.gz"),
                binaries={n: h for n, h in b["files"].items() if n.endswith(".so")},
            ),
        )
        names.extend(("package.json", "receiver-source.tar.gz"))
    return names


def seal(work, out):
    plan = whole_iq.read(work / "plan.json")
    if plan["sources"] != trial.sources():
        raise ValueError("as-run sources differ from plan")
    for build in plan["builds"].values():
        if trial.installation(Path(build["root"])) != build:
            raise ValueError("installed sources differ from plan")
    rows, timings, decisions, imports = {method: [] for method in FILES}, [], {}, {}
    out.mkdir(parents=True, exist_ok=True)
    names = ["source-lock.json", "parity.json", "imports.json", "resources.csv", *FILES.values()]
    for ident in trial.ROSTER:
        match = plan["bindings"][ident]
        if match != trial.binding(ident):
            raise ValueError("the archived binding changed during qualification")
        outputs, imports[ident] = {}, {}
        for method in FILES:
            row = verified_attempt(work, plan, ident, method)
            outputs[method] = row
            timings.append(resources(row))
            imports[ident][method] = row["measures"].get("imports")
            rows[method].append(
                dict(
                    id=ident,
                    method=method,
                    tile=match["tile"],
                    native_sha256=match["native_sha256"],
                    catalog_sha256=match["catalog_sha256"],
                    input_sha256=match["request_sha256"],
                    cohort="held" if ident == trial.HELD else "coverage",
                    result=row["result"],
                )
            )
            for filename in ("attempt.json", "service.log"):
                name = f"{ident}-{method}-{filename}.gz"
                data = (work / ident / method / filename).read_bytes()
                write(out / name, gzip.compress(data, mtime=0))
                names.append(name)
        decisions[ident] = parity(outputs[trial.STOCK], outputs[trial.CANDIDATE])
    publish = (
        all(
            set(p["identical_arms"]) == set(ARMS)
            and all(p["identical_arms"].values())
            and p["identical_publication"]
            and p["identical_counters_and_scores"]
            and {"ranked", "initial", "conservative", "nomination"}
            <= p["identical_decisions"].keys()
            and all(p["identical_decisions"].values())
            for p in decisions.values()
        )
        and decisions["DS29-0357"]["stock_cavity_trials"] > 0
    )
    names.extend(measure_source(plan, out, publish=publish))
    for method, name in FILES.items():
        pack(out / name, rows[method])
    write(out / "source-lock.json", (work / "plan.json").read_bytes())
    save_json(out / "parity.json", dict(qualified=publish, comparisons=decisions))
    save_json(out / "imports.json", imports)
    csv_file(out / "resources.csv", timings)
    save_json(
        out / "receipt.json",
        dict(cases=list(trial.ROSTER), files={name: _sha(out / name) for name in names}),
    )


def score(out):
    seal = whole_iq.read(out / "receipt.json")
    for name, digest in seal["files"].items():
        whole_iq.checked(out / name, digest)
    truth, original = _frozen_roof()
    scored = []
    for method, name in FILES.items():
        positions = read_predictions(out / name)
        if set(positions) != set(trial.ROSTER):
            raise ValueError("closed predictions differ from the declared cohort")
        for ident, row in positions.items():
            if (
                row["native_sha256"] != original[ident]["native"]["sha256"]
                or row["catalog_sha256"] != original[ident]["catalog"]["sha256"]
            ):
                raise ValueError("scoring authority differs from scientific inputs")
            for arm in ARMS:
                fix = row["result"]["arms"][arm]
                scored.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        status=row["result"]["status"],
                        geographic_error_km=distance_km(fix["latlon"], truth[ident]["truth"]),
                        conditional_RMS_hz=fix.get("rf_rms_hz"),
                        frequency_objective=row["result"]["metrics"].get(f"{arm}_frequency_score"),
                    )
                )
    csv_file(out / "scores.csv", scored)
    save_json(
        out / "figure-lock.json",
        dict(cases=seal["cases"], files=seal["files"] | {"scores.csv": _sha(out / "scores.csv")}),
    )
    chart = dict(
        id="acquisition-frontier-compact-cut",
        method=trial.CANDIDATE,
        scope="roof",
        cases=seal["cases"],
        seal="figure-lock.json",
        title="Compact v5 with direct numerical bindings",
        caption=(
            "Three same-core pairs from the original capture-era GLRT factors under 512 MiB "
            "and zero swap. DS26-0090 was held by a salted choice. "
            "DS29-0357 covers cavity recovery."
        ),
        provenance=["parity.json", "resources.csv", "scores.csv"],
        series=[
            dict(
                key="one",
                file=FILES[trial.CANDIDATE],
                value=trial.CANDIDATE,
                label="Direct compact bindings",
            ),
            dict(
                key="stock",
                file=FILES[trial.STOCK],
                value=trial.STOCK,
                label="Phase-release compact v5",
                match=list(MATCH),
            ),
        ],
    )
    save_json(out / "figures.json", dict(version=1, charts=[chart]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    seal(args.work, local_output(trial.REPORT))
    score(trial.REPORT)
