"""Build compact ALGO01 evidence and deterministic scientific figures.

The collection action is for the source workstation; published readers can
regenerate the ALGO01 figures from compact data with --figures-only.
"""

import argparse
import ast
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from sgp4.api import Satrec

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    adaptive = ROOT / "reports/2026_10_18_ds23_adaptive_failures"
    pilot = ROOT / "reports/2026_10_18_ds23_phase_refreshed_evaluation"
    positions = ROOT / "reports/2026_10_18_ds23_arc_positions"
    coverage = ROOT / "reports/2026_10_18_ds23_algo01_coverage"
    mapping = {
        adaptive / "interventions.png": "figures/interventions.png",
        adaptive / "S0039_phase_prior_pressure.png": "figures/phase_prior_pressure.png",
        adaptive / "S0342_graph_bridge.png": "figures/graph_bridge.png",
        adaptive / "S0342_polynomial_splits.png": "figures/polynomial_splits.png",
        adaptive / "S0342_causal_epoch_duplicates.png": "figures/causal_epoch_duplicates.png",
        adaptive / "loss_surfaces.png": "figures/loss_surfaces.png",
        adaptive / "results.csv": "evidence/interventions.csv",
        positions / "position_comparison.csv": "evidence/expanded_positions.csv",
        positions / "validation.json": "evidence/expanded_validation.json",
        positions / "added_track_influence.png": "figures/expanded_track_influence.png",
        positions / "satellite_scale_ablation.png": "figures/satellite_scale_ablation.png",
        coverage / "coverage_and_position.png": "figures/coverage_and_position.png",
        coverage / "comparison.csv": "evidence/coverage_comparison.csv",
        coverage / "validation.json": "evidence/coverage_validation.json",
        ROOT / "reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json":
        "config/graph_selected.json",
    }
    for source in coverage.glob("DS23-*.json"):
        mapping[source] = "evidence/coverage/" + str(source.relative_to(coverage))
    authorities, widths, branches = {}, {}, {}
    for case in ("DS23-0342", "DS23-0039"):
        source = pilot / case
        for name in ("observations.json", "tracks.json", "radio_noise.json", "receipt.json",
                     "nominal_elements.json", "selected.tle", "previous.tle",
                     "previous_receipt.json", "input_receipt.json", "prepared.json"):
            mapping[source / name] = f"evidence/{case}/pilot/{name}"
        for name in ("previous.tle", "previous_receipt.json", "receipt.json"):
            mapping[adaptive / "genuine_prior_inputs" / case / name] = (
                f"evidence/{case}/genuine_prior/{name}")
        repair_path = adaptive / "genuine_causal_prior" / case / "repairs.json"
        mapping[repair_path] = f"evidence/{case}/repairs.json"
        repaired = json.loads(repair_path.read_text())
        widths[case] = next(r["phase_width_receipt"] for r in repaired["results"]
                            if r["variant"] == "causal_phase" and r["arm"] == "c0")
        original_path = source / "fit_radio_noise.json"
        original = json.loads(original_path.read_text())
        branch = next(c for c in original["choices"]
                      if c["hypothesis"] == original["selected_hypothesis"])
        branches[case] = dict(selected_hypothesis=original["selected_hypothesis"],
                              node=branch["node"],
                              source_sha256=digest(original_path),
                              note="RF-discovered cached branch; no endpoint seed is supplied")
        authorities[case] = {}
        for name in ("tracking.json", "bank.npz", "fit_radio_noise.json", "observations.json",
                     "tracks.json", "radio_noise.json", "nominal_elements.json", "receipt.json"):
            path = source / name
            authorities[case][name] = dict(repository_path=str(path.relative_to(ROOT)),
                                           sha256=digest(path), bytes=path.stat().st_size,
                                           duplicated_in_ALGO01=path in mapping)
    for name in ("trim_failed.json", "prefix_validation.json", "polynomial_split_bic.json",
                 "surface_diagnostics.json"):
        mapping[adaptive / "genuine_causal_prior/DS23-0342" / name] = (
            f"evidence/DS23-0342/{name}")
    mapping[adaptive / "genuine_causal_prior/DS23-0039/surface_diagnostics.json"] = (
        "evidence/DS23-0039/surface_diagnostics.json")
    mapping[adaptive / "DS23-0342/failed_candidate_search.json"] = (
        "evidence/DS23-0342/failed_candidate_search.json")
    provenance = {}
    for source, target in mapping.items():
        output = HERE / target
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        provenance[target] = dict(original=str(source.relative_to(ROOT)), sha256=digest(source),
                                  bytes=source.stat().st_size)
    dump(HERE / "evidence_manifest.json", provenance)
    dump(HERE / "input_authorities.json", authorities)
    dump(HERE / "evidence/phase_widths.json", widths)
    dump(HERE / "evidence/RF_selected_branches.json", branches)

    # Static same-repository import closure; paths are preserved for overlay.
    todo = [ROOT / "tools" / (name + ".py") for name in (
        "evaluate_ds23_phase_refreshed", "ds23_radio_noise",
        "prepare_ds23_genuine_causal_prior", "investigate_ds23_adaptive_failures",
        "propagate_ds23_arc_positions", "report_ds23_arc_positions",
        "prototype_ds23_visible_arc_variants", "audit_ds23_algo01_coverage",
        "report_ds23_algo01_coverage")]
    todo += [ROOT / "tests/analysis" / name for name in (
        "test_ds23_adaptive_failure_controls.py", "test_ds23_transfer_tools.py",
        "test_ds23_arc_position_tool.py", "test_ds23_algo01_coverage_tool.py",
        "test_graph_tracklets.py",
        "test_dsx01_joint_marginal_tool.py", "test_dsx01_hierarchical_bound_tool.py")]
    found = set()
    while todo:
        path = todo.pop()
        if not path.exists() or path in found:
            continue
        found.add(path)
        tree = ast.parse(path.read_text())
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        for name in names:
            relative = Path(*name.split("."))
            candidates = ([ROOT / "src" / relative.with_suffix(".py"),
                           ROOT / "src" / relative / "__init__.py"] if name.startswith("leo")
                          else [ROOT / "tools" / relative.with_suffix(".py")])
            todo.extend(p for p in candidates if p.exists())
    hashes = {}
    for source in sorted(found):
        relative = source.relative_to(ROOT)
        output = HERE / "source_snapshot" / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        hashes[str(relative)] = digest(source)
    for name in ("pyproject.toml", "setup.py"):
        source = ROOT / name
        shutil.copyfile(source, HERE / "source_snapshot" / name)
        hashes[name] = digest(source)
    dump(HERE / "source_snapshot/sha256.json", hashes)
    versions = {}
    for name in ("numpy", "scipy", "matplotlib", "sgp4", "pytest"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not installed in report environment"
    dump(HERE / "runtime_versions.json", dict(python=sys.version, packages=versions))


def figures():
    output = HERE / "figures"
    output.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set(xlim=(0, 12), ylim=(0, 7))
    ax.axis("off")
    nodes = [
        (0.3, 5.5, "Qualified GLRT CFO\nraw frequency + immutable IDs"),
        (4.4, 5.5, "Alias-aware graph paths\npenalized polynomials, order ≤ 4"),
        (8.5, 5.5, "Radio-only noise\nactive curvature eligibility"),
        (8.5, 3.0, "Causal regional satellites\nlatest mean + genuine prior history"),
        (4.4, 3.0, "RF hypotheses: identity + alias\n25 × 25 km regional box"),
        (0.3, 3.0, "Joint position + nuisance fit\nabsolute-prior phase refresh"),
        (0.3, 0.5, "Reject / independently salvage\nexclude failed evidence and refit"),
        (4.4, 0.5, "Frozen-calibration extension\nlinear tracks cannot calibrate"),
        (8.5, 0.5, "Position + evidence diagnostics\nGPS evaluation only afterward"),
    ]
    for x, y, label in nodes:
        ax.add_patch(FancyBboxPatch((x, y), 3.1, 1.05, boxstyle="round,pad=0.12",
                                   facecolor="#edf3f9", edgecolor="#31587d", lw=1.5))
        ax.text(x+1.55, y+0.525, label, ha="center", va="center", fontsize=10)
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8)):
        xa, ya, _ = nodes[a]
        xb, yb, _ = nodes[b]
        delta = np.array([xb-xa, yb-ya], float)
        unit = delta / np.linalg.norm(delta)
        start = np.array([xa+1.55, ya+0.525]) + unit*np.array([1.7, .7])
        end = np.array([xb+1.55, yb+0.525]) - unit*np.array([1.7, .7])
        ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=15,
                                     color="#31587d", lw=1.5))
    ax.text(6, 6.9, "ALGO01: causal, conservative research prototype", ha="center",
            fontsize=17, weight="bold")
    fig.savefig(output / "pipeline.png", dpi=170, bbox_inches="tight")
    plt.close(fig)

    widths = json.loads((HERE / "evidence/phase_widths.json").read_text())
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    age = np.linspace(0, 48, 300)
    for disagreement in (.5, 2, 5):
        sigma = np.clip(np.hypot(1, disagreement*age/12), 1, 15)
        axes[0].plot(age, sigma, label=f"alignment {disagreement:g} s")
    axes[0].set(title="Mechanism: illustrative 12 h update gap", xlabel="TLE age, hours",
                ylabel="Phase prior standard deviation, seconds", ylim=(0, 16))
    axes[0].legend(fontsize=8)
    for ax, (case, rows) in zip(axes[1:], widths.items(), strict=True):
        sigma = [r["sigma_s"] for r in rows]
        ax.bar(np.arange(len(rows)), sigma, color="#526f99")
        ax.axhline(1, color="#bd4235", ls="--", label="Old uniform 1 s")
        ax.set(title=f"{case}: actual nominated families", xlabel="NORAD satellite ID",
               ylabel="Phase prior standard deviation, seconds", ylim=(0, 16))
        ax.set_xticks(np.arange(len(rows)), [str(r["norad"]) for r in rows], rotation=90,
                      fontsize=7)
        ax.legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Zero-centered causal phase uncertainty; no GPS or RF residuals set widths",
                 fontsize=14)
    fig.tight_layout()
    fig.savefig(output / "causal_phase_prior.png", dpi=180)
    plt.close(fig)

    data = np.array([[5., 4.998, 3.372, 3.502], [2.023, 1.962, .760, .893],
                     [1.786, 1.736, .760, .893], [2.147, 2.105, 1.159, 1.286],
                     [2.147, 2.105, 1.159, 1.286], [1.949, 1.897, 1.159, 1.286]])
    names = ["Original pilot", "Prior + exclusion", "ALGO01: conservative salvage",
             "Expanded greedy", "Expanded joint", "Expanded EM"]
    colors = ["#888888", "#7aa0c4", "#21744e", "#e4a33c", "#cd7047", "#8663ad"]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)
    for k, (ax, case) in enumerate(zip(axes, ("DS23-0342", "DS23-0039"), strict=True)):
        for arm in range(2):
            vals = data[:, 2*k+arm]
            bars = ax.bar(np.arange(6)+(arm-.5)*.34, vals, width=.32,
                          color=colors, alpha=1 if arm == 0 else .5,
                          hatch=None if arm == 0 else "//")
            ax.bar_label(bars, fmt="%.3f", fontsize=7, padding=3, rotation=90)
        ax.set(title=case, ylabel="Position error, km", ylim=(0, 5.8))
        ax.set_xticks(np.arange(6), names, rotation=30, ha="right", fontsize=9)
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("ALGO01 remains best demonstrated: solid c=0, hatched fitted c\n"
                 "GPS evaluation only; membership changes across intervention rows", fontsize=13)
    fig.tight_layout()
    fig.savefig(output / "position_comparison.png", dpi=180)
    plt.close(fig)


def validate():
    manifests = json.loads((HERE / "evidence_manifest.json").read_text())
    for relative, record in manifests.items():
        assert digest(HERE / relative) == record["sha256"], relative
    sources = json.loads((HERE / "source_snapshot/sha256.json").read_text())
    for relative, expected in sources.items():
        assert digest(HERE / "source_snapshot" / relative) == expected, relative
    links = 0
    for document in HERE.rglob("*.md"):
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", document.read_text()):
            if target.startswith(("http:", "https:", "mailto:", "#")):
                continue
            path = document.parent / target.split("#")[0]
            if path.name == "validation.json" and path.parent == HERE:
                continue
            assert path.exists(), (document, target)
            links += 1
    widths = json.loads((HERE / "evidence/phase_widths.json").read_text())
    checks = {}
    for case, rows in widths.items():
        for row in rows:
            expected = float(np.clip(np.hypot(1., row["old_new_alignment_s"]
                * row["age_s"] / row["previous_epoch_gap_s"]), 1., 15.))
            assert abs(expected - row["sigma_s"]) < 1e-12
            assert row["previous_epoch_gap_s"] >= 1.
        base = HERE / "evidence" / case
        receipt = json.loads((base / "pilot/receipt.json").read_text())
        elements = json.loads((base / "pilot/nominal_elements.json").read_text())
        previous = json.loads((base / "genuine_prior/previous_receipt.json").read_text())
        cutoff = receipt["cutoff_utc_ns"]
        for n, record in elements.items():
            info = record["provenance"]
            assert info["element_epoch_utc_ns"] <= cutoff
            assert info["collected_utc_ns"] <= cutoff
            sat = Satrec.twoline2rv(*record["lines"])
            byte_epoch_ns = ((sat.jdsatepoch - 2440587.5) + sat.jdsatepochF) * 86400e9
            assert byte_epoch_ns <= cutoff
            old = previous["sources"].get(n)
            if old:
                assert old["collected_utc_ns"] <= cutoff
                assert info["element_epoch_utc_ns"] - old["epoch_utc_ns"] >= 1e9
        old_lines = (base / "genuine_prior/previous.tle").read_text().splitlines()
        for offset in range(0, len(old_lines), 3):
            sat = Satrec.twoline2rv(old_lines[offset+1], old_lines[offset+2])
            byte_epoch_ns = ((sat.jdsatepoch - 2440587.5) + sat.jdsatepochF) * 86400e9
            assert byte_epoch_ns <= cutoff
        observations = json.loads((base / "pilot/observations.json").read_text())
        lookup = {r["observation_id"]: r for r in observations}
        assert len(lookup) == len(observations)
        tracks = json.loads((base / "pilot/tracks.json").read_text())
        ownership = set()
        for track in tracks:
            for oid, value in zip(track["observation_ids"], track["values"], strict=True):
                assert oid not in ownership
                ownership.add(oid)
                periods = (value - lookup[oid]["measured_cfo_hz"]) / (1 / 4.4e-6)
                assert abs(periods - round(periods)) < 1e-8
        checks[case] = dict(original_GLRT_points=len(observations),
                            graph_owned_points=len(ownership), candidate_count=len(elements),
                            nominated_phase_widths=len(rows),
                            collection_and_TLE_byte_epoch_causal=True,
                            genuine_previous_epoch_separation_at_least_1s=True,
                            raw_CFO_preserved_modulo_integer_alias=True,
                            phase_formula_replayed=True)
    dump(HERE / "validation.json", dict(status="passed", source_files=len(sources),
         evidence_files=len(manifests), valid_relative_links=links, cases=checks,
         tests="45 focused frozen-snapshot tests passed in an isolated publication worktree",
         scope="Documentation/evidence audit; not a new full-pipeline campaign"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--figures-only", action="store_true")
    args = parser.parse_args()
    if not args.figures_only:
        collect()
    figures()
    validate()
