"""Isolated slope-bound experiment; frozen baseline scientific files stay unchanged."""

import hashlib
import json
import time
import types

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from bundle import Data
from evaluate import coordinates, ecef, write_csv
from investigate_sample import SESSION, save
from run_case import save_atomic
from selection import MODEL_NAMES, ROOT


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one slope experiment patch site: {old!r}")
    return source.replace(old, new, 1)


def load_source(name, source, original_path):
    module = types.ModuleType(name)
    module.__file__ = str(original_path)
    exec(compile(source, str(original_path), "exec"), module.__dict__)
    return module


def build_variant(output, slope_bound=50.0):
    output.mkdir(parents=True, exist_ok=True)
    refinement_path = ROOT.parent / "2026_10_02_coherent_localization/refinement.py"
    refinement = refinement_path.read_text()
    refinement = replace_once(
        refinement,
        "-np.inf, -10.0, -np.inf, -10.0,",
        f"-np.inf, -{slope_bound}, -np.inf, -{slope_bound},",
    )
    refinement = replace_once(
        refinement, "np.inf, 10.0, np.inf, 10.0,", f"np.inf, {slope_bound}, np.inf, {slope_bound},"
    )
    refinement = replace_once(refinement, ">= 10 - 1e-7", f">= {slope_bound} - 1e-7")
    variant_refinement = output / "refinement.py"
    variant_refinement.write_text(refinement)
    source = (ROOT / "models.py").read_text()
    source = replace_once(
        source,
        '0.0 if mode == "constant" else 10.0',
        f'0.0 if mode == "constant" else {slope_bound}',
    )
    source = replace_once(source, "weights, line, 10.0)", f"weights, line, {slope_bound})")
    source = replace_once(
        source, 'COHERENT_ROOT / "refinement.py"', f"Path({str(variant_refinement)!r})"
    )
    (output / "models.py").write_text(source)
    robust = (ROOT / "robust_weighted_drift.py").read_text()
    robust = replace_once(
        robust,
        "for slope in (-10.0, 0.0, 10.0):",
        f"for slope in (-{slope_bound}, 0.0, {slope_bound}):",
    )
    robust = replace_once(
        robust,
        "            -10,\n            10,",
        f"            -{slope_bound},\n            {slope_bound},",
    )
    robust = replace_once(
        robust, "RX slopes bounded +/-10 Hz/s.", f"RX slopes bounded +/-{slope_bound} Hz/s."
    )
    (output / "robust_weighted_drift.py").write_text(robust)
    return (
        load_source("slope50_models", source, ROOT / "models.py"),
        load_source("slope50_robust", robust, ROOT / "robust_weighted_drift.py"),
    )


def run_robust(data, baseline, models, robust):
    identities = {
        row["track_index"]: row["satellite_index"]
        for row in baseline["track_independent"]["tracks"]
    }
    arrays, numbers, initial, tracks = models._validate_data(data)
    context = models._Context(data, arrays, numbers, initial, tracks, float("inf"))

    def evaluate(point):
        prediction, visible = context.cache.get(point)
        blocks = models._track_blocks(context, prediction, visible)
        return robust.fit_blocks(blocks, identities)

    started = time.monotonic()
    result = models._search_position(
        evaluate, baseline["track_independent"]["parameters"][:2], time.monotonic() + 180
    )
    parameters = np.zeros(70)
    parameters[:2] = result["point"]
    for receiver, line in result["details"].items():
        parameters[2 + receiver * 2 : 4 + receiver * 2] = line
    return {
        "parameters": parameters,
        "success": result["success"],
        "status": result["status"],
        "objective": result["objective"],
        "elapsed_s": time.monotonic() - started,
        "search": {key: result[key] for key in ("grid_best", "local_runs")},
    }


def compare(output, baseline, results, directory):
    reference = json.loads((directory / "evaluation.json").read_text())["reference_site"]
    reference_ecef = ecef(reference["latitude_deg"], reference["longitude_deg"])
    rows = []
    for name in [*MODEL_NAMES, "robust_weighted"]:
        row = {"model": name}
        for limit, fits in ((10, baseline), (50, results)):
            fitted = fits[name]
            parameters = np.asarray(fitted["parameters"])
            row[f"status_{limit}"] = fitted["status"]
            row[f"success_{limit}"] = fitted["success"]
            row[f"error_km_{limit}"] = float(
                np.linalg.norm(ecef(*coordinates(parameters[:2])) - reference_ecef)
            )
            row[f"rx0_slope_{limit}"] = (
                float(parameters[3]) if name != "track_independent" else None
            )
            row[f"rx1_slope_{limit}"] = (
                float(parameters[5]) if name != "track_independent" else None
            )
            row[f"objective_{limit}"] = fitted.get("objective")
        rows.append(row)
    write_csv(output / "comparison.csv", rows)
    save_atomic(
        output / "comparison.json",
        {
            "session_id": SESSION,
            "rows": rows,
            "caveat": "Same inputs and initialization, no known-location RX initialization. "
            "Bound was chosen after inspecting this scan; exploratory, not heldout.",
        },
    )
    figure, axis = plt.subplots(figsize=(12, 8), constrained_layout=True)
    indices = np.arange(len(rows))
    for bound, shift, color in ((10, -0.18, "#777777"), (50, 0.18, "#0072b2")):
        bars = axis.barh(
            indices + shift,
            [row[f"error_km_{bound}"] for row in rows],
            height=0.34,
            label=f"±{bound} Hz/s",
            color=color,
        )
        for bar, row in zip(bars, rows, strict=True):
            if not row[f"success_{bound}"]:
                bar.set_hatch("///")
        axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=8)
    axis.set_yticks(indices, [row["model"] for row in rows])
    axis.invert_yaxis()
    axis.set_xlabel("Reference position error (km); hatched bars indicate nonconvergence")
    axis.legend()
    axis.set_title(
        SESSION + " — slope-bound comparison\n"
        "Same initialization; satellite timing priors unchanged"
    )
    save(figure, output, "slope-bound-comparison")
    print(json.dumps(rows, indent=2))


def main():
    directory = ROOT / "scans" / SESSION
    investigation = ROOT / f"investigation-{SESSION}"
    output = investigation / "slope50"
    output.mkdir(exist_ok=True)
    if (output / "fits.json").exists():
        raise RuntimeError("Existing slope50 receipts: inspect process/results before rerunning")
    data = Data(directory)
    baseline = json.loads((directory / "fits.json").read_text())["models"]
    models, robust = build_variant(output)
    receipt = {
        "session_id": SESSION,
        "slope_bound_hz_s": 50,
        "status": "running",
        "models": {},
        "input_sha256": {
            name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ("bundle.json", "bundle.npz", "fits.json")
        },
        "generated_source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in output.glob("*.py")
        },
        "initialization": "Same frozen bundle initial prior, not known-site heatmap result",
        "time_shift_bounds": "Unchanged: +/-3 s and +/-10 s satellite timing experiments",
    }

    def checkpoint(results):
        receipt["models"] = results
        save_atomic(output / "fits.json", receipt)
        print(
            json.dumps(
                {
                    "models_finished": len(results),
                    "statuses": {name: row["status"] for name, row in results.items()},
                }
            ),
            flush=True,
        )

    checkpoint({})
    results = models.run_models(data, checkpoint=checkpoint)
    results["robust_weighted"] = run_robust(data, baseline, models, robust)
    receipt["status"] = "finished"
    checkpoint(results)
    baseline["robust_weighted"] = json.loads(
        (investigation / "robust-weighted-drift.json").read_text()
    )
    compare(output, baseline, results, directory)


if __name__ == "__main__":
    main()
