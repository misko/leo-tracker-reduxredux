"""Seal saved-IQ boundary evidence and compare measured detector costs."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean

from ..__main__ import local_output, save_json, write
from ..variants.iq_stream import _read_prefix
from . import capture_raw_boundary as trial
from .full_v5_check import BULK, _load_case, _sha, compare_probes


def rf_inventory(case, probes):
    targets, manifests = {}, []
    for raw in case["recording"]["segments"]:
        data = _read_prefix(BULK / raw["path"], 65537)
        if len(data) > 65536 or hashlib.sha256(data).hexdigest() != raw["sha256"]:
            raise ValueError("stored detector configuration manifest changed")
        summary = json.loads(data)
        manifests.append(raw["sha256"])
        for t in summary["configuration"]["targets"]:
            label = t["channel"], t["edge"]
            value = t["rf_center_hz"]
            if targets.setdefault(label, value) != value:
                raise ValueError("capture has ambiguous target centre across segments")
    return dict(
        manifests=manifests,
        center_hz=dict(
            Counter(str(targets[r["channel"], r["edge"]] - r["actual_rf_hz"]) for r in probes)
        ),
    )


def count(rows):
    return sum(len(r["candidates"]) for r in rows)


def controls(row):
    captures = {}
    source = row["probes"]
    for name, candidate in row.get("controls", {}).items():
        values = candidate["probes"]
        if name == "swap-receivers":
            values = [
                dict(data, receiver_id=original["receiver_id"])
                for original, data in zip(source, reversed(values), strict=True)
            ]
        captures[name] = dict(
            visit=row["visit"],
            positive_exact=trial.positives(values) == trial.positives(source),
            rows_exact=source == values,
            positives=count(trial.positives(values)),
            capture_positives=count(trial.positives(source)),
            probe_calls=len(candidate["calls"]),
        )
    return captures


def collect(work, output):
    lock = (work / "source-lock.json").read_bytes()
    if json.loads(lock)["files"] != trial.sources():
        raise ValueError("held detector numerical source changed")
    output.mkdir(parents=True, exist_ok=True)
    files = ["source-lock.json"]
    write(output / files[0], lock)
    result = {}
    for ident in trial.PINS:
        prefix, held = (work / (ident + suffix) for suffix in ("-prefix", "-held"))
        p = json.loads((prefix / "summary.json").read_bytes())
        raw = (held / "result.json.gz").read_bytes()
        h = json.loads(gzip.decompress(raw))
        rows = h["rows"]
        if h["case"] != ident or {(x["segment"], x["sequence"]) for x in rows} != {
            (segment, sequence)
            for segment, sequences in trial.ROSTER.items()
            for sequence in sequences
        }:
            raise ValueError("held visit roster differs from the protocol")
        valid = [r for r in rows if r["status"] == "processed"]
        native, native_sha = trial.ordinary_factor(ident)
        if native_sha != h["ordinary_factor_sha256"]:
            raise ValueError("ordinary factor authority changed")
        all_inputs = all(
            r["production"]["dwell"]["ci16_exact_unscaled"]
            and all(
                c["probe_sha256"]
                == r["production"]["dwell"]["probe_input_sha256"][c["receiver_id"]]
                for c in r["production"]["calls"]
            )
            for r in valid
        )
        visits = p["archived_status_counts"]["processed_windows"]
        matches = [
            compare_probes(left, right, p["sample_rate_hz"])
            for row in valid
            for left, right in zip(row["probes"], row["ordinary"]["probes"], strict=True)
        ]
        timing = dict(
            prefix_capture_cpu_s=mean(p["production_cpu_s_per_valid_window"]),
            held_capture_cpu_s=mean(r["production"]["cpu_s"] for r in valid),
            held_accelerated_cpu_s=mean(r["accelerated"]["cpu_s"] for r in valid),
            held_ordinary_c_cpu_s=mean(r["ordinary"]["cpu_s"] for r in valid),
            ideal_max_cpu_for_300_s_per_valid=600 / visits,
        )
        result[ident] = dict(
            scheduled=len(rows),
            processed=len(valid),
            full_valid_visits=visits,
            exact_iq_bytes_two_readers=True,
            exact_production_abi=all_inputs,
            archive_exact_valid_visits=sum(r["exact_archive"] for r in valid),
            ordinary_archive_exact_valid_visits=sum(
                r["ordinary"]["exact_ordinary_archive"] for r in valid
            ),
            accelerated_exact_positive_visits=sum(
                r["accelerated"]["positive_exact"] for r in valid
            ),
            fallback_used_visits=sum(len(r["production"]["calls"]) > 2 for r in valid),
            capture_and_ordinary_positives_exact=sum(
                trial.positives(r["probes"]) == trial.positives(r["ordinary"]["probes"])
                for r in valid
            ),
            positives={
                "capture": sum(count(trial.positives(r["probes"])) for r in valid),
                **{
                    m: sum(count(trial.positives(r[m]["probes"])) for r in valid)
                    for m in ("ordinary", "accelerated")
                },
            },
            held_alias_matching=dict(
                matched=sum(len(r["positive_matches"]) for r in matches),
                capture_only=sum(r["production_only"] for r in matches),
                ordinary_only=sum(r["native_only"] for r in matches),
            ),
            metadata=h["metadata"],
            rf_inventory=rf_inventory(_load_case(ident), native["source"]["probes"]),
            timing=timing,
            ideal_two_core_detector_wall_s={
                m: v * visits / 2
                for m, v in timing.items()
                if m != "ideal_max_cpu_for_300_s_per_valid"
            },
            controls=[controls(r) for r in valid],
        )
        for name, data in (
            (ident + "-held.json.gz", raw),
            (ident + "-prefix.json", (prefix / "summary.json").read_bytes()),
            (
                ident + "-prefix-visits.json.gz",
                gzip.compress((prefix / "visits.jsonl").read_bytes(), mtime=0),
            ),
        ):
            write(output / name, data)
            files.append(name)
    diagnostic = work / "positive-prefix/positive-prefix.json.gz"
    if diagnostic.is_file():
        raw = diagnostic.read_bytes()
        saved = json.loads(gzip.decompress(raw))
        source = work / "DS29-0082-prefix/visits.jsonl"
        if saved["prefix_sha256"] != _sha(source) or saved["source_lock_sha256"] != _sha(
            work / "source-lock.json"
        ):
            raise ValueError("positive-prefix check no longer matches its exact input")
        name = "DS29-0082-positive-prefix.json.gz"
        write(output / name, raw)
        files.append(name)
    save_json(output / "comparison.json", result)
    files.append("comparison.json")
    save_json(output / "receipt.json", dict(files={name: _sha(output / name) for name in files}))
    return result


def figure(output, result):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 3.8), layout="constrained")
    methods = (
        ("Capture-era", "prefix_capture_cpu_s"),
        ("Accelerated capture-era", "held_accelerated_cpu_s"),
        ("Ordinary C", "held_ordinary_c_cpu_s"),
    )
    y = list(range(len(methods)))
    for delta, (case, values) in zip((-0.16, 0.16), result.items(), strict=True):
        data = [values["ideal_two_core_detector_wall_s"][k] for _, k in methods]
        ax.scatter(data, [z + delta for z in y], s=52, label=case, zorder=3)
    ax.set_yticks(y, labels=[label for label, _ in methods])
    ax.invert_yaxis()
    ax.axvline(300, color="black", linewidth=1, linestyle="--", label="300 s service budget")
    ax.set_xscale("log")
    ax.set_xlabel("Projected detector wall time on two ideal cores (s)")
    ax.set_title("Measured visits projected to each full recording")
    ax.grid(axis="x", alpha=0.2)
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(output / "detector-cost.png", dpi=150)
    plt.close(fig)
    path = output / "receipt.json"
    receipt = json.loads(path.read_bytes())
    receipt["files"]["detector-cost.png"] = _sha(output / "detector-cost.png")
    save_json(path, receipt)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    args = p.parse_args()
    dest = local_output(args.out)
    figure(dest, collect(args.work, dest))
