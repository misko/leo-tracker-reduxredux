"""Seal the paired source-distribution results and produce their position charts."""

import argparse
import gzip
from pathlib import Path

from ..__main__ import encoded, local_output, references, save_json, write
from . import cavity_payload_trial as trial
from .full_receiver_comparison import read, require_fields, sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_cavity_scores import arm_scores


def publish(work, out):
    plan = read(work / "plan.json")
    files, rows, timings, paired, attempts = [], [], [], {}, []
    out.mkdir(parents=True, exist_ok=True)
    for key, (pin, order) in trial.CASES.items():
        binding = plan["bindings"][key]
        both = {}
        for label in order:
            source = work / "runs" / key / label
            row = read(source / "attempt.json")
            require_fields(row, dict(binding, cpu=pin, method="v5_cavity_payload_" + label))
            samples = row.pop("measurements")
            proof = samples.get("proof")
            if proof is not None:
                require_fields(proof, dict(cpu=pin, memory=512 * 2**20, swap=0))
            finish = samples.get("finish", {})
            if row["exit_code"] == 0:
                if not proof or finish["eval_modules"] or not samples.get("origins"):
                    raise ValueError("unexpected or missing runtime provenance")
                for path in samples["origins"].values():
                    name = str(Path(path).relative_to(work / label))
                    if name not in plan["packages"][label]["files"]:
                        raise ValueError(f"loaded module outside declared source set: {name}")
            both[label] = row["result"]
            rows.append(dict(row, mode="matched-tile"))
            attempts.append(
                dict(
                    case=key,
                    distribution=label,
                    measurements=samples,
                    stdout_sha256=sha(source / "stdout"),
                    stderr_sha256=sha(source / "stderr"),
                )
            )
            timings.append(
                dict(
                    id=row["id"],
                    detector=row["detector"],
                    distribution=label,
                    pin=pin,
                    status=row["result"]["status"],
                    wall_s=row["wall_s"],
                    cpu_s=finish.get("cgroup_cpu_s"),
                    cgroup_peak_bytes=finish.get("cgroup_peak"),
                    imported_project_paths=len(set(samples.get("origins", {}).values())),
                    reached_paths=finish.get("paths"),
                    reached_code_locations=finish.get("execution_locations"),
                )
            )
        paired[key] = dict(
            c0=both["full"]["arms"]["c0"] == both["small"]["arms"]["c0"],
            fitted_c=both["full"]["arms"]["fitted_c"] == both["small"]["arms"]["fitted_c"],
            all_science=trial.scientific_result(both["full"])
            == trial.scientific_result(both["small"]),
        )
    pack(out / "positions.jsonl.gz", rows)
    write(out / "observations.json.gz", gzip.compress(encoded(attempts), mtime=0))
    write(out / "source-lock.json", (work / "plan.json").read_bytes())
    write(out / "receiver-source.tar.gz", (work / "small.tar.gz").read_bytes())
    if sha(out / "receiver-source.tar.gz") != plan["packages"]["small"]["archive_sha256"]:
        raise ValueError("distribution archive changed")
    save_json(out / "package.json", plan["packages"]["small"])
    save_json(out / "parity.json", paired)
    csv_file(out / "resources.csv", timings)
    files = [
        "positions.jsonl.gz",
        "observations.json.gz",
        "source-lock.json",
        "receiver-source.tar.gz",
        "package.json",
        "parity.json",
        "resources.csv",
    ]
    save_json(
        out / "prediction-lock.json",
        dict(cases=list(trial.CASES), files={n: sha(out / n) for n in files}),
    )
    ids = [row["id"] for row in rows]
    truth = {r["id"]: r["truth"] for r in references("roof16", ids)[1]}
    csv_file(
        out / "scores.csv",
        [
            dict(s, method=r["method"], detector=r["detector"])
            for r in rows
            for s in arm_scores(r, truth[r["id"]])
        ],
    )
    charts = []
    for detector in ("ordinary", "capture-era"):
        cases = [v["id"] for v in plan["bindings"].values() if v["detector"] == detector]
        series = []
        for label, series_key, title in (
            ("small", "one", "Small source package"),
            ("full", "stock", "Full source package"),
        ):
            spec = dict(
                key=series_key,
                file="positions.jsonl.gz",
                label=title,
                value="v5_cavity_payload_" + label,
                where=dict(detector=detector),
            )
            if detector == "ordinary":
                spec["native_authority"] = "ordinary"
            if label == "full":
                spec["match"] = ["input_sha256", "native_sha256", "catalog_sha256", "tile"]
            series.append(spec)
        lock = detector + "-lock.json"
        save_json(
            out / lock,
            dict(
                cases=cases,
                files={
                    n: sha(out / n)
                    for n in (
                        "positions.jsonl.gz",
                        "parity.json",
                        "resources.csv",
                        "scores.csv",
                        "source-lock.json",
                    )
                },
            ),
        )
        charts.append(
            dict(
                id="cavity-payload-" + detector,
                method="v5_cavity_payload_small",
                scope="roof",
                title="Standalone position receiver with a smaller distribution",
                caption=f"{detector.capitalize()} factors. Same recording across both packages; "
                "512 MiB, zero swap. Original v5 options used capture-era factors.",
                seal=lock,
                cases=cases,
                provenance=["resources.csv", "parity.json", "scores.csv"],
                series=series,
            )
        )
    save_json(out / "figures.json", dict(version=1, charts=charts))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.work.resolve(), local_output(args.out))
