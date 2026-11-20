"""Publish the capped direct cavity outcomes and authentic lifetime control."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import direct_cavity_cap as cap
from . import direct_cavity_trial as direct
from . import working_memory_trial
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

ROOT = direct.common.ROOT
REPORT = ROOT / cap.REPORT
LIFETIME = REPORT.parent / "whole-pair"
FIELDS = ("native_sha256", "catalog_sha256", "tile")
SERIES = {
    cap.BOUNDED: ("positions.jsonl.gz", "one", "Parser cut"),
    cap.DIRECT: ("stock-positions.jsonl.gz", "stock", "Staged"),
    "whole_cavity": ("lifetime-positions.jsonl.gz", "one_native_factors", "Lifetime cavity"),
}


def verify_attempt(row, binding, cpu):
    direct.common.require_fields(row, dict(binding, cpu=cpu))
    (proof,) = row["proof"]
    if (
        proof["cpu"] != cpu
        or proof["nice"] < 10
        or not row["live"]
        or any(
            s["memory.max"] != cap.MEMORY
            or s["memory.swap.max"] != 0
            or s["memory.swap.current"] != 0
            for s in (proof, *row["live"], *row["stages"])
        )
        or row["service_result"] != row["kernel"].get("Result")
        or row["wall_s"] > cap.LIMIT + 6
    ):
        raise ValueError("worker receipt does not establish the measured service limit")
    if row["service_result"] == "oom-kill" and (
        row["kernel"]["ExecMainStatus"] != "9"
        or int(row["kernel"]["MemoryPeak"]) != cap.MEMORY
        or row["result"]["status"] != "failed"
        or any(v["latlon"] is not None for v in row["result"]["arms"].values())
    ):
        raise ValueError("kernel OOM must preserve failure and absent position arms")
    validate_result(row["result"])


def seal(work, out):
    plan_path, alternate_path = (work / k for k in ("plan.json", "bounded-lock.json"))
    plan, alternate = (direct.common.read(p) for p in (plan_path, alternate_path))
    if plan["source"] != cap.source(direct):
        raise ValueError("original release or capped trial source changed")
    if alternate["bundle_sha256"] != direct.common.sha(work / "bounded-bundle.json"):
        raise ValueError("alternative staged bundle manifest changed")
    previous_seal = direct.common.seal(
        LIFETIME, "prediction-lock.json", ("positions.jsonl.gz", "stages.json.gz")
    )
    prior = LIFETIME / "source-lock.json"
    if direct.common.sha(prior) != previous_seal["source_lock_sha256"]:
        raise ValueError("lifetime worker input authority changed")
    lifetime = read_predictions(LIFETIME / "positions.jsonl.gz")
    previous = direct.common.read(prior)["inputs"]
    direct_positions = read_predictions(direct.REPORT / "positions.jsonl.gz")
    out.mkdir(parents=True, exist_ok=True)
    files = []
    rows = {m: [] for m in SERIES}
    comparison, resources = {}, []
    for key, cpu in plan["pins"].items():
        binding = plan["inputs"][key]
        ident = binding["id"]
        p = previous[ident]
        reference = lifetime[ident]
        direct.common.require_fields(reference, {k: binding[k] for k in FIELDS})
        direct.common.require_fields(direct_positions[ident], binding)
        prior_request = Path(p["prior_request_path"])
        if (
            p["prior_request_sha256"] != binding["frozen_request_sha256"]
            or direct.common.sha(prior_request) != binding["frozen_request_sha256"]
            or working_memory_trial.canonical_request(prior_request) != binding["input_sha256"]
            or reference["result"]["arms"] != direct_positions[ident]["result"]["arms"]
        ):
            raise ValueError("lifetime control lost its same-request scientific equality")
        rows["whole_cavity"].append(reference)
        comparison[ident] = dict(lifetime_matches_unrestricted_direct=True, capped={})
        for method, auth in ((cap.DIRECT, plan), (cap.BOUNDED, alternate)):
            source = work / "runs" / key / method
            raw = source / "measurement.json"
            if (
                method == cap.DIRECT
                and direct.common.sha(raw) != alternate["baseline_measurements"][key]
            ):
                raise ValueError("baseline measurement changed after the alternative was staged")
            row = direct.common.read(raw)
            verify_attempt(row, binding, cpu)
            direct.common.require_fields(
                row,
                dict(
                    method=method,
                    bundle_sha256=auth["bundle_sha256"],
                    source_lock_sha256=direct.common.sha(plan_path),
                ),
            )
            log = source / "service.log"
            if direct.common.sha(log) != row["log_sha256"]:
                raise ValueError("measurement and recorded terminal log differ")
            name = f"{ident}-{method}-service.log.gz"
            write(out / name, gzip.compress(log.read_bytes(), mtime=0))
            files.append(name)
            rows[method].append(row)
            result = row["result"]
            comparison[ident]["capped"][method] = dict(
                status=result["status"],
                terminal=row["service_result"],
                exact_unrestricted=(
                    result["arms"] == direct_positions[ident]["result"]["arms"]
                    if result["status"] == "ok"
                    else None
                ),
            )
            stages = row["stages"]
            initial = next((s for s in stages if s["name"] == "initial_selection"), {})
            resources.append(
                dict(
                    id=ident,
                    method=method,
                    cpu=cpu,
                    status=result["status"],
                    service_result=row["service_result"],
                    latest_stage=stages[-1]["name"],
                    wall_s=row["wall_s"],
                    cpu_s=int(row["kernel"]["CPUUsageNSec"]) / 1e9,
                    cgroup_memory_peak_bytes=int(row["kernel"]["MemoryPeak"]),
                    max_sampled_swap_bytes=max(r["memory.swap.current"] for r in row["live"]),
                    through_initial_entry_peak_bytes=initial.get("memory.peak"),
                    cgroup_cpu_s_at_initial_entry=initial.get("cpu_s"),
                )
            )
    for method, values in rows.items():
        name = SERIES[method][0]
        pack(out / name, values)
        files.append(name)
    for target, origin in (
        ("source-lock.json", plan_path),
        ("bounded-lock.json", alternate_path),
        ("bounded-bundle.json", work / "bounded-bundle.json"),
    ):
        write(out / target, origin.read_bytes())
        files.append(target)
    save_json(out / "parity.json", comparison)
    csv_file(out / "resources.csv", resources)
    receipt = dict(
        cases=list(comparison),
        source_lock_sha256=direct.common.sha(out / "source-lock.json"),
        lifetime_source_lock_sha256=previous_seal["source_lock_sha256"],
        lifetime_prediction_sha256=previous_seal["files"]["positions.jsonl.gz"],
        files={
            name: direct.common.sha(out / name) for name in (*files, "parity.json", "resources.csv")
        },
    )
    save_json(out / "receipt.json", receipt)
    return rows, receipt


def score(out, rows, receipt):
    truth, _ = _frozen_roof()
    scored = []
    for method, cases in rows.items():
        for row in cases:
            for arm in ARMS:
                result = row["result"]
                endpoint = result["arms"][arm]
                scored.append(
                    dict(
                        id=row["id"],
                        method=method,
                        arm=arm,
                        status=result["status"],
                        error_km=distance_km(endpoint["latlon"], truth[row["id"]]["truth"]),
                        conditional_rms_hz=endpoint.get("rf_rms_hz"),
                    )
                )
    csv_file(out / "scores.csv", scored)
    receipt = dict(
        receipt,
        files=dict(receipt["files"], **{"scores.csv": direct.common.sha(out / "scores.csv")}),
    )
    save_json(out / "figure-lock.json", receipt)
    exhausted = {
        method
        for method in (cap.BOUNDED, cap.DIRECT)
        if all(row["service_result"] == "oom-kill" for row in rows[method])
    }
    caption = (
        "Both direct entries were OOM-killed on both inputs. The prior "
        "same-input 512 MiB lifetime service returned both arms."
        if len(exhausted) == 2
        else "The staged direct pair and prior lifetime cavity used the same stored factors."
    )
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="direct-cavity-cap-ordinary",
                    method=cap.BOUNDED,
                    scope="roof",
                    cases=receipt["cases"],
                    title="Direct compact v5 cavity at 512 MiB",
                    seal="figure-lock.json",
                    caption=caption,
                    provenance=["scores.csv", "resources.csv", "parity.json", "bounded-lock.json"],
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    series=[
                        dict(
                            file=name,
                            key=key,
                            label=f"{label} · OOM" if method in exhausted else label,
                            value=method,
                            native_authority="ordinary",
                            **(
                                {"match": list(direct.MATCH if method == cap.DIRECT else FIELDS)}
                                if key != "one"
                                else {}
                            ),
                        )
                        for method, (name, key, label) in SERIES.items()
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    args = p.parse_args()
    target = local_output(args.out)
    score(target, *seal(args.work, target))
