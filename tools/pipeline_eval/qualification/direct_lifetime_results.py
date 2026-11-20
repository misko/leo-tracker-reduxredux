"""Seal standalone capped lifetime predictions, controls, and deployable source."""

import argparse
import gzip
import json
import re
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import direct_cavity_trial as direct
from . import direct_lifetime_bundle as build
from . import direct_lifetime_trial as trial
from . import working_memory_trial
from .direct_cavity_results import pack_release
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

METHOD = "v5_direct_lifetime"
LIFETIME = direct.REPORT.parent / "whole-pair"
ARCHIVE = {
    METHOD: ("positions.jsonl.gz", "one", "Direct lifetime"),
    direct.DIRECT: ("stock-positions.jsonl.gz", "stock", "Uncapped direct"),
    "whole_cavity": ("lifetime-positions.jsonl.gz", "one_native_factors", "Prior lifetime"),
    direct.STOCK: ("secant-positions.jsonl.gz", "all_visits", "Uncapped secant"),
}
FIELD = ("native_sha256", "catalog_sha256", "tile")


def whole_cpu(log):
    value = re.search(r"CPU time consumed: ([^\n]+)", log)
    if value is None:
        return None
    tokens = re.findall(r"(\d+(?:\.\d+)?)(min|ms|us|h|s)", value[1])
    scale = {"h": 3600, "min": 60, "s": 1, "ms": 1e-3, "us": 1e-6}
    return sum(float(quantity) * scale[unit] for quantity, unit in tokens) if tokens else None


def validate_cap(row, plan, key):
    cpu = plan["cases"][key]
    direct.common.require_fields(row, dict(plan["inputs"][key], method=METHOD, cpu=cpu))
    (proof,) = row["observations"]["proof"]
    if (
        proof["cpu"] != cpu
        or proof["nice"] < 10
        or proof["memory"] != trial.MEMORY
        or proof["swap"] != 0
        or proof["tmpdir"] != str(trial.TMP)
        or not row["live"]
        or any(
            x["memory.max"] != trial.MEMORY
            or x["memory.swap.max"] != 0
            or x["memory.swap.current"] != 0
            for x in row["live"]
        )
        or row["wall_s"] > trial.LIMIT + 6
    ):
        raise ValueError("receipt did not establish the cgroup and affinity")
    if row["result"]["status"] == "ok":
        (finish,) = row["observations"]["finish"]
        if (
            row["service_result"] != "success"
            or row["returncode"] != 0
            or finish["cgroup_peak"] > trial.MEMORY
            or finish["eval_modules"]
            or finish["paths"] != len(set(row["observations"]["reached"]))
            or any(x["events"]["oom_kill"] for x in row["live"])
        ):
            raise ValueError("successful numerical result lacks matching process proof")
    validate_result(row["result"])


def archived_control(source, plan):
    receipt = direct.common.seal(
        source, "prediction-lock.json", ("positions.jsonl.gz", "stages.json.gz")
    )
    lock = source / "source-lock.json"
    if direct.common.sha(lock) != receipt["source_lock_sha256"]:
        raise ValueError("capped lifetime source lock changed")
    control, samples = (
        read_predictions(source / "positions.jsonl.gz"),
        json.loads(gzip.decompress((source / "stages.json.gz").read_bytes())),
    )
    prior = direct.common.read(lock)["inputs"]
    for i in plan["inputs"].values():
        ident = i["id"]
        file = Path(prior[ident]["prior_request_path"])
        if (
            prior[ident]["prior_request_sha256"] != i["frozen_request_sha256"]
            or direct.common.sha(file) != i["frozen_request_sha256"]
            or working_memory_trial.canonical_request(file) != i["input_sha256"]
        ):
            raise ValueError("lifetime control used a different scientific request")
        direct.common.require_fields(control[ident], {k: i[k] for k in FIELD})
    return receipt, control, samples


def seal(work, out):
    work_lock, bundle = work / "plan.json", work / "bundle.json"
    plan = direct.common.read(work_lock)
    if direct.common.sha(bundle) != plan["bundle_sha256"]:
        raise ValueError("source specialization changed since lock")
    prior = direct.common.seal(
        direct.REPORT,
        "receipt.json",
        (
            "positions.jsonl.gz",
            "stock-positions.jsonl.gz",
        ),
    )
    if prior != plan["unrestricted_direct"]:
        raise ValueError("earlier direct receipt changed")
    prior_direct = read_predictions(direct.REPORT / "positions.jsonl.gz")
    prior_secant = read_predictions(direct.REPORT / "stock-positions.jsonl.gz")
    prior_lifetime, lifetime, samples = archived_control(LIFETIME, plan)
    out.mkdir(parents=True, exist_ok=True)
    names = [pack_release(work / direct.RELEASE, bundle, out)]
    for p, name in ((work_lock, "source-lock.json"), (bundle, "bundle.json")):
        write(out / name, p.read_bytes())
        names.append(name)
    source_payload = {
        name: (work / "executed-sources" / name).read_text() for name in plan["source"]
    }
    for name, expected in plan["source"].items():
        if direct.common.sha(work / "executed-sources" / name) != expected:
            raise ValueError("executed qualification source changed")
    save_json(out / "executed-sources.json", source_payload)
    names.append("executed-sources.json")
    results = {m: [] for m in ARCHIVE}
    timing, parity = [], {}
    for key in plan["cases"]:
        binding = plan["inputs"][key]
        ident = binding["id"]
        produced = work / "runs" / key
        row = direct.common.read(produced / "attempt.json")
        validate_cap(row, plan, key)
        direct.common.require_fields(
            row,
            dict(
                source_lock_sha256=direct.common.sha(work_lock),
                bundle_sha256=plan["bundle_sha256"],
            ),
        )
        log = produced / "service.log"
        if row["log_sha256"] != direct.common.sha(log):
            raise ValueError("sealed cgroup output changed")
        logname = ident + "-service.log.gz"
        write(out / logname, gzip.compress(log.read_bytes(), mtime=0))
        names.append(logname)
        direct.common.require_fields(prior_direct[ident], binding)
        direct.common.require_fields(prior_secant[ident], binding)
        controls = {
            direct.DIRECT: prior_direct[ident],
            direct.STOCK: prior_secant[ident],
            "whole_cavity": lifetime[ident],
        }
        result = row["result"]
        ok = result["status"] == "ok"
        profile = next(iter(row["observations"]["finish"]), {})
        observed = row["observations"]["stage"]
        parity[ident] = dict(
            service_result=row["service_result"],
            status=result["status"],
            controls={
                m: dict(
                    coordinates={
                        a: result["arms"][a]["latlon"] == c["result"]["arms"][a]["latlon"]
                        for a in ARMS
                    },
                    conditional_rms={
                        a: result["arms"][a].get("rf_rms_hz")
                        == c["result"]["arms"][a].get("rf_rms_hz")
                        for a in ARMS
                    },
                )
                for m, c in controls.items()
            }
            if ok
            else {},
            exact_frequency_objective={
                a: result["metrics"].get(f"{a}_frequency_score")
                == prior_direct[ident]["result"]["metrics"][f"{a}_frequency_score"]
                for a in ARMS
            }
            if ok
            else None,
            caveat="Prior capped control measured its position stage "
            "inside an IQ service on CPU 18",
        )
        results[METHOD].append(row)
        for method, value in controls.items():
            results[method].append(value)
        timing.append(
            dict(
                id=ident,
                method=METHOD,
                scope="full capped stored-native service",
                cpu=row["cpu"],
                status=result["status"],
                wall_s=row["wall_s"],
                cpu_s=whole_cpu(log.read_text()),
                numerical_exit_cpu_s=profile.get("cgroup_cpu_s"),
                peak_charge_bytes=profile.get(
                    "cgroup_peak", max(x["memory.peak"] for x in row["live"])
                ),
                peak_rss_kib=profile.get("peak_rss_kib"),
                reached_paths=len(row["observations"]["reached"]),
                reached_code_entries=profile.get("execution_locations"),
                last_stage=(observed[-1] if observed else {}).get("name"),
            )
        )
        for method in (direct.DIRECT, direct.STOCK):
            value = controls[method]
            elapsed = value["resources"]
            timing.append(
                dict(
                    id=ident,
                    method=method,
                    scope="uncapped stored-native launcher",
                    cpu=value["cpu"],
                    status=value["result"]["status"],
                    wall_s=elapsed["wall_s"],
                    cpu_s=elapsed["cpu_s"],
                    peak_rss_kib=elapsed["child_peak_rss_kib"],
                )
            )
        ns = samples[ident]["position"]
        timing.append(
            dict(
                id=ident,
                method="whole_cavity",
                scope="position stage of whole-IQ capped service",
                cpu=18,
                status="ok",
                wall_s=ns["end"]["monotonic_s"] - ns["start"]["monotonic_s"],
                cpu_s=(ns["end"]["cpu.stat.usage_usec"] - ns["start"]["cpu.stat.usage_usec"]) / 1e6,
                peak_rss_kib=ns["end"]["rss_peak_kib"],
            )
        )
    for method, records in results.items():
        file = ARCHIVE[method][0]
        pack(out / file, records)
        names.append(file)
    keys = tuple(dict.fromkeys(k for row in timing for k in row))
    csv_file(out / "resources.csv", [{k: row.get(k) for k in keys} for row in timing])
    save_json(out / "parity.json", parity)
    receipt = dict(
        cases=list(parity),
        source_lock_sha256=direct.common.sha(out / "source-lock.json"),
        lifetime=prior_lifetime,
        unrestricted_direct=prior,
        files={n: direct.common.sha(out / n) for n in (*names, "resources.csv", "parity.json")},
    )
    save_json(out / "receipt.json", receipt)
    return results, receipt


def score(out, results, receipt):
    refs, _ = _frozen_roof()
    csv_file(
        out / "scores.csv",
        [
            dict(
                id=r["id"],
                method=method,
                arm=arm,
                status=r["result"]["status"],
                error_km=distance_km(r["result"]["arms"][arm]["latlon"], refs[r["id"]]["truth"]),
                conditional_rms_hz=r["result"]["arms"][arm].get("rf_rms_hz"),
            )
            for method, rows in results.items()
            for r in rows
            for arm in ARMS
        ],
    )
    receipt = dict(
        receipt, files={**receipt["files"], "scores.csv": direct.common.sha(out / "scores.csv")}
    )
    save_json(out / "figure-lock.json", receipt)
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="direct-lifetime-cavity-cap",
                    method=METHOD,
                    scope="roof",
                    cases=receipt["cases"],
                    title="Standalone compact cavity under 512 MiB",
                    seal="figure-lock.json",
                    caption="Same stored factors and both calibrations. Direct lifetime ran in "
                    "512 MiB with zero swap. Controls preserve their original resource scopes.",
                    provenance=["scores.csv", "resources.csv", "parity.json"],
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    series=[
                        dict(
                            key=key,
                            file=file,
                            value=method,
                            label=label,
                            native_authority="ordinary",
                            **(
                                {"match": list(FIELD if method == "whole_cavity" else direct.MATCH)}
                                if key != "one"
                                else {}
                            ),
                        )
                        for method, (file, key, label) in ARCHIVE.items()
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=build.REPORT)
    a = p.parse_args()
    output = local_output(a.out)
    score(output, *seal(a.work, output))
