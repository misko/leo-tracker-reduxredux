"""Seal the two direct receiver runs against the earlier stdin-policy decisions."""

import argparse
import gzip
from pathlib import Path

import check_install as trial

from tools.pipeline_eval import cavity_runtime, whole_iq
from tools.pipeline_eval.__main__ import local_output, save_json, write
from tools.pipeline_eval.qualification.cavity_payload_trial import scientific_result
from tools.pipeline_eval.qualification.phase_support_results import pack
from tools.pipeline_eval.qualification.prefix_figures import csv_file
from tools.pipeline_eval.qualification.whole_pressure_trial import rows_from
from tools.pipeline_eval.scoring import ARMS, distance_km

DIRECT, REFERENCE = "installed_interior", "phase_release_guard_20m"
MATCH = ["input_sha256", "native_sha256", "catalog_sha256", "tile", "request_sha256"]


def publish(work):
    out = trial.HERE
    planfile = work / "plan.json"
    plan = whole_iq.read(planfile)
    legacy = whole_iq.read(work / "compatibility.json")
    profiles = set(cavity_runtime.PROFILES) - {"interior"}
    if (
        set(legacy["comparisons"]) != profiles
        or not all(v["equal"] for v in legacy["comparisons"].values())
        or legacy["current_builder_sha256"] != trial.HASH(Path(cavity_runtime.__file__))
        or plan["builder_sha256"] != legacy["current_builder_sha256"]
        or plan["harness_sha256"] != trial.HASH(Path(trial.__file__))
        or plan["protocol_sha256"] != trial.HASH(out / "PROTOCOL.md")
        or plan["files"] != whole_iq.receiver_identity(work / "interior")
        or plan["native_sources"] != whole_iq.native_sources(work / "interior")
    ):
        raise ValueError("installed package does not match the completed compatibility check")
    before = trial.parent.REPORT
    lock = whole_iq.read(
        whole_iq.checked(before / "prediction-lock.json", plan["measured_parent_sha256"])
    )
    authority = whole_iq.read(before / "figure-lock.json")
    queries = whole_iq.read(
        whole_iq.checked(before / "figure-queries.json", authority["files"]["figure-queries.json"])
    )["queries"]
    queries = [q for q in queries if q["id"] in trial.PINS]
    prior_rows = {
        r["id"]: r
        for r in rows_from(
            whole_iq.checked(before / "positions.jsonl.gz", lock["files"]["positions.jsonl.gz"])
        )
        if r["method"] == REFERENCE
    }
    predictions, timings, parity, raw = [], {}, {}, []
    if {q["id"] for q in queries} != set(trial.PINS):
        raise ValueError("missing authenticated query")
    for query in queries:
        ident = query["id"]
        ref = prior_rows[ident]
        run = work / ident
        path = run / "receipt.json"
        receipt = whole_iq.read(path)
        if receipt["id"] != ident or receipt["plan_sha256"] != trial.HASH(planfile):
            raise ValueError("integrated attempt receipt has a different prior")
        for name, key in (("position.json", "output_sha256"), ("service.log", "log_sha256")):
            whole_iq.checked(run / name, receipt[key])
        actual = receipt["result"]
        proof = before / (ident + "-guard-on.json")
        expected = whole_iq.read(whole_iq.checked(proof, lock["files"][proof.name]))
        if expected != ref["result"] or any(
            ref[k] != query["bindings"][k] or ref[k] != plan["offers"][ident]["offer"][k]
            for k in MATCH
        ):
            raise ValueError("reference decision or offer has changed")
        success = receipt["returncode"] == 0 and receipt["service_result"] == "success"
        parity[ident] = dict(
            expected_status=expected["status"],
            observed_status=actual["status"],
            exact_except_stage_timing=(
                scientific_result(expected) == scientific_result(actual)
                and expected["boundary"] == actual["boundary"]
            )
            if success
            else None,
        )
        peak, cpu = (receipt["kernel"].get(k, "") for k in ("MemoryPeak", "CPUUsageNSec"))
        samples = receipt["samples"]
        timings[ident] = dict(
            status=receipt["service_result"],
            supervisor_wall_s=receipt["wall_s"],
            charged_peak_bytes=(
                int(peak) if peak.isdecimal() else max(s["memory.peak"] for s in samples)
            ),
            cgroup_cpu_s=int(cpu) / 1e9 if cpu.isdecimal() else max(s["cpu_s"] for s in samples),
            observed_one_process_cpu=receipt["pids"],
        )
        for source in (path, run / "position.json", run / "service.log"):
            label = ident + "-" + source.name + ".gz"
            write(out / label, gzip.compress(source.read_bytes(), mtime=0))
            raw.append(label)
        predictions.extend([ref, dict(ref, method=DIRECT, result=actual)])
    pack(out / "positions.jsonl.gz", predictions)
    save_json(out / "queries.json", dict(queries=queries))
    save_json(out / "resources.json", timings)
    save_json(out / "parity.json", parity)
    for source, name in (
        (planfile, "source-lock.json"),
        (work / "compatibility.json", "compatibility.json"),
        (work / "previous-builder.py.gz", "previous-builder.py.gz"),
        (work / "interior" / "__main__.py", "installed-entry.py.txt"),
        (work / "interior" / cavity_runtime.INTERIOR_RULE, "installed-rule.py.txt"),
    ):
        write(out / name, source.read_bytes())
    names = (
        "positions.jsonl.gz",
        "queries.json",
        "source-lock.json",
        "compatibility.json",
        "resources.json",
        "parity.json",
        "previous-builder.py.gz",
        "installed-entry.py.txt",
        "installed-rule.py.txt",
        "PROTOCOL.md",
        "check_install.py",
        "check_legacy.py",
        *raw,
    )
    save_json(
        out / "prediction-lock.json",
        dict(cases=list(trial.PINS), files={name: trial.HASH(out / name) for name in names}),
    )
    truth = {q["id"]: q for q in queries}
    scores = []
    for entry in predictions:
        ident, result = entry["id"], entry["result"]
        for arm in ARMS:
            value = result["arms"][arm]
            scores.append(
                dict(
                    id=ident,
                    recording=truth[ident]["recording"],
                    arm=arm,
                    method=entry["method"],
                    status=result["status"],
                    geographic_error_km=distance_km(value["latlon"], truth[ident]["truth"]),
                    forced_error_km=distance_km(value.get("forced_latlon"), truth[ident]["truth"]),
                    conditional_RMS_hz=value.get("rf_rms_hz"),
                    frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                )
            )
    csv_file(out / "scores.csv", scores)
    names += ("scores.csv", "prediction-lock.json")
    save_json(
        out / "figure-lock.json",
        dict(cases=list(trial.PINS), files={name: trial.HASH(out / name) for name in names}),
    )
    chart = dict(
        version=1,
        charts=[
            dict(
                id="installed-interior",
                method=DIRECT,
                scope="transfer",
                title="Installed 20 m interior profile on two recorded offers",
                caption=(
                    "Fresh direct entry versus the exact earlier post-filter decision "
                    "on the same archived native factors, causal TLEs and offered tile."
                ),
                cases="sealed",
                seal="figure-lock.json",
                queries="queries.json",
                condition_labels={
                    "near-inside": "Containing offer",
                    "near-outside": "Near omission",
                },
                provenance=["compatibility.json", "resources.json", "parity.json", "scores.csv"],
                series=[
                    dict(
                        key=key,
                        value=mode,
                        file="positions.jsonl.gz",
                        label=label,
                        forced_label=forced,
                        **({"match": MATCH} if key == "stock" else {}),
                    )
                    for key, mode, label, forced in (
                        ("candidate", DIRECT, "Installed interior", "Installed forced endpoint"),
                        ("stock", REFERENCE, "Earlier stdin filter", "Earlier forced endpoint"),
                    )
                ],
            )
        ],
    )
    save_json(out / "figures.json", chart)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    publish(local_output(p.parse_args().work))
