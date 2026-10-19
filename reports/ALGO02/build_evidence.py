"""Collect the ALGO02 research freeze and regenerate figures from compact evidence."""

import argparse
import ast
import csv
import hashlib
import importlib.metadata
import json
import platform
import shutil
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    predictive = ROOT / "reports/2026_10_19_ds23_predictive_linear"
    phase = ROOT / "reports/2026_10_18_ds23_history_calibrated_phase"
    mapping = {}
    for name in ("summary.json", "positions.csv", "extension_counts.csv", "failed_components.csv",
                 "validation.json", "protocol.json", "causal_receipt_audit.json", "execution.json",
                 "evidence.tar.xz", "evidence_inventory.json"):
        mapping[predictive / name] = "evidence/predictive/" + name
    for name in ("summary.json", "comparison.csv", "protocol.json", "validation.json"):
        mapping[phase / name] = "evidence/phase/" + name
    for name in ("position_errors.png", "points_and_accuracy.png", "scan217_linear_predictions.png"):
        mapping[predictive / name] = "figures/" + name
    mapping[phase / "position_error_by_scan.png"] = "figures/phase_position_errors.png"
    mapping[ROOT / "reports/ALGO01/config/graph_selected.json"] = "config/graph_selected.json"
    mapping[ROOT / "reports/2026_10_19_algo02_qualification/replay_comparison.json"] = "evidence/engine_replay_qualification.json"
    for case in ("DS23-0001", "DS23-0002"):
        mapping[ROOT / "reports/2026_10_19_algo02_qualification" / ("cold_" + case + ".json")] = "evidence/cold_" + case + ".json"
    campaign = ROOT / "reports/2026_10_19_algo02_ds23_full"
    if (campaign / "protocol.json").exists():
        for name in ("protocol.json", "sample.json"):
            mapping[campaign / name] = "execution/" + name
    provenance = {}
    for source, target in mapping.items():
        output = HERE / target
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        provenance[target] = dict(original=str(source.relative_to(ROOT)), sha256=digest(source),
                                  bytes=source.stat().st_size)
    write(HERE / "evidence_manifest.json", provenance)
    roots = ["evaluate_ds23_phase_refreshed", "run_algo01_ds23_sample", "ds23_radio_noise",
             "prepare_ds23_genuine_causal_prior", "investigate_ds23_adaptive_failures",
             "evaluate_ds23_family_weighting", "export_ds23_causal_history",
             "learn_ds23_causal_phase_forecast", "probe_ds23_history_calibrated_phase",
             "ds23_predictive_linear", "probe_ds23_predictive_linear", "run_ds23_predictive_linear",
             "algo02_scan", "prepare_algo02_ds23", "run_algo02_ds23", "report_algo02_ds23"]
    todo = [ROOT / "tools" / (name + ".py") for name in roots]
    todo.extend((ROOT / "tests/analysis").glob("test_ds23_predictive_linear_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_ds23_history_calibrated_phase_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_ds23_family_weighting_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_ds23_causal_phase_mean_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_algo02_scan_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_prepare_algo02_ds23_tool.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_algo02_ds23_runner.py"))
    todo.extend((ROOT / "tests/analysis").glob("test_algo02_ds23_report.py"))
    found = set()
    while todo:
        path = todo.pop()
        if not path.is_file() or path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                relative = Path(*name.split("."))
                candidates = [ROOT / "src" / relative.with_suffix(".py"), ROOT / "src" / relative / "__init__.py"]
                if "." not in name:
                    candidates.append(ROOT / "tools" / (name + ".py"))
                todo.extend(p for p in candidates if p.is_file())
    found.update([ROOT / "setup.py", ROOT / "pyproject.toml"])
    if (campaign / "protocol.json").exists():
        protocol = read(campaign / "protocol.json")
        for name, expected in protocol["source_sha256"].items():
            source = ROOT / name
            if digest(source) != expected:
                raise ValueError("full-corpus frozen source changed: " + name)
            found.add(source)
    hashes = {}
    for source in sorted(found):
        output = HERE / "source_snapshot" / source.relative_to(ROOT)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        hashes[str(output.relative_to(HERE / "source_snapshot"))] = digest(output)
    write(HERE / "source_snapshot/sha256.json", hashes)
    write(HERE / "runtime_versions.json", dict(python=platform.python_version(),
          packages={name: importlib.metadata.version(name) for name in ("numpy", "matplotlib", "sgp4", "pytest")}))


def figures():
    figdir = HERE / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    phase = read(HERE / "evidence/phase/summary.json")["results"]
    linear = read(HERE / "evidence/predictive/summary.json")["position"]
    methods = [("ALGO01", phase["original"]), ("RX support + 300 Hz", phase["baseline"]),
               ("Causal phase history", phase["mean_and_distribution"]), ("ALGO02", linear["all_linear"])]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for axis, metric in zip(axes, ("mean_km", "median_km"), strict=True):
        x = np.arange(len(methods))
        for j, arm in enumerate(("c0", "fitted_c")):
            values = [value[arm][metric] for _, value in methods]
            bars = axis.bar(x + (j - .5) * .36, values, .36, label=arm, color=("#4477aa", "#ee7733")[j])
            axis.bar_label(bars, fmt="%.3f", fontsize=8)
        axis.axhline(.5, color="#777777", ls="--", lw=1, label="0.5 km objective")
        axis.set_xticks(x, [name for name, _ in methods], rotation=18, ha="right")
        axis.set_title(metric.replace("_km", "").title() + " position error")
        axis.set_ylabel("km");axis.grid(axis="y", alpha=.2);axis.set_axisbelow(True)
    axes[0].legend(fontsize=8)
    fig.suptitle("Same 20 DS23 development scans; all failures retained through paired fallback")
    fig.tight_layout();fig.savefig(figdir / "performance_stages.png", dpi=180);plt.close(fig)

    with (HERE / "evidence/predictive/positions.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    outcomes = {}
    for arm in ("c0", "fitted_c"):
        selected = [r for r in rows if r["arm"] == arm and r["method"] == "all_linear"]
        values = np.array([float(r["policy_error_km"]) for r in selected])
        outcomes[arm] = dict(count=len(values), mean_km=float(values.mean()), median_km=float(np.median(values)),
                             p90_km=float(np.quantile(values, .9)), maximum_km=float(values.max()),
                             below_half_km=int((values < .5).sum()), below_1km=int((values < 1).sum()))
        expected = linear["all_linear"][arm]
        assert abs(outcomes[arm]["mean_km"] - expected["mean_km"]) < 1e-12
        assert abs(outcomes[arm]["median_km"] - expected["median_km"]) < 1e-12
    write(HERE / "evidence/development_summary.json", outcomes)

    fig, ax = plt.subplots(figsize=(13, 7));ax.set_xlim(0, 13);ax.set_ylim(0, 7);ax.axis("off")
    boxes = [(0.2, 5.1, 2.65, 1.1, "Qualified GLRT observations\nRF / RX / channel / time\nOne original probe identity"),
             (3.2, 5.1, 2.65, 1.1, "Alias-aware graph tracks\nOrder 0–4 + penalties\nActive curvature selection"),
             (6.2, 5.1, 2.65, 1.1, "Broad causal RF discovery\nLatest eligible TLE mean\n25 × 25 km cold region"),
             (9.2, 5.1, 3.1, 1.1, "Curved-only calibration\nRX / band / drift / orbit\nCausal phase-history prior"),
             (5.6, 2.65, 3.45, 1.25, "Frozen linear extensions\nPredict from curved posterior\nFull shared covariance"),
             (9.2, 2.65, 3.1, 1.25, "Position optimization\nCurved bound + prediction\n5 phase rounds × 48 steps"),
             (9.2, .35, 3.1, 1.25, "Matched c0 / fitted-c gates\nBoth pass → ALGO02 pair\nOtherwise curved-pair fallback"),
             (.35, 2.2, 4.4, 1.55, "Per-scan causal TLE history (≤72 h)\nAll regional candidate identities\nPast-update train / validation split\nNo previous RF position or GPS")]
    for x, y, w, h, label in boxes:
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=.08", fc="#edf4fa", ec="#4477aa"))
        ax.text(x + w / 2, y + h / 2, label, ha="center", va="center", fontsize=10)
    for a, b in [((2.9, 5.65), (3.1, 5.65)), ((5.9, 5.65), (6.1, 5.65)),
                 ((8.9, 5.65), (9.1, 5.65)), ((10.75, 5), (10.75, 4)),
                 ((7.3, 5), (7.3, 4)), ((9.1, 3.25), (9.15, 3.25)),
                 ((10.75, 2.5), (10.75, 1.7)), ((4.8, 3.8), (9.1, 5.1))]:
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=16, color="#555555"))
    ax.text(3, .7, "Linear points constrain position.\nThey do not update calibration at fixed position.", ha="center", fontsize=11, weight="bold")
    fig.suptitle("ALGO02-v1: single-scan RF position with causal external orbital history", fontsize=15)
    fig.tight_layout();fig.savefig(figdir / "pipeline.png", dpi=180);plt.close(fig)
    write(HERE / "validation.json", dict(development_table_recomputed_from_120_CSV_rows=True,
          rows=len(rows), c_arms=["c0", "fitted_c"], all20_in_each_policy_denominator=True,
          underlying_predictive_validation=read(HERE / "evidence/predictive/validation.json"),
          source_files=len(read(HERE / "source_snapshot/sha256.json")),
          no_full_DS23_accuracy_claim=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--figures-only", action="store_true")
    args = parser.parse_args()
    if not args.figures_only:
        collect()
    figures()
