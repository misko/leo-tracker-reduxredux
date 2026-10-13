"""Publish measured initialization diagnostics without interpreting score as accuracy."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import WrappedConfig
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider
from tools.report_glrt_relative_phase import surface_summary
from tools.report_wrapped_physical_diagnostics import replay_endpoint

SCANS = (
    "fast-862e4fbdc0d1b5b03a0ef5e12422eaf0",
    "fast-bf660cb5200c4a27c3a2181a6dfc7132",
)
STUDIES = (
    "joint-satellite-bias-expanded-v1",
    "bias-shape-reference-full-v1",
    "bias-shape-local-v1",
    "bias-shape-convergence-irls-v1",
    "bias-shape-convergence-lbfgs-v1",
    "bias-shape-local-converged-v1",
    "bias-shape-transport-local-v1",
    "bias-shape-reciprocal-reference-v1",
    "bias-shape-reciprocal-one-outer-reference-v1",
    "bias-shape-reciprocal-local-v1",
)


def diagnostic_summary(result, rows, arm):
    summary = surface_summary(result, rows, arm)
    reference = rows[0]["arms"][arm]
    best = max(rows, key=lambda r: r["arms"][arm]["score"])["arms"][arm]
    summary["best_density_gain"] = best["log_ratio"] - reference["log_ratio"]
    summary["best_charged_penalty_change"] = (
        best["log_ratio"] - best["score"] - reference["log_ratio"] + reference["score"]
    )
    if (
        result["search_plan"]["random_points"] == 0
        or result["search_plan"]["refinement_rounds"] == 0
    ):
        summary["conditional_gate_met"] = None
        summary["gate_scope"] = "Reference fit or bounded probe; no spatial accuracy gate"
    else:
        summary["gate_scope"] = "Conditional development profile; no independent validation"
    return summary


def compact_receipts(output):
    """Preserve parsed values and both byte hashes while reducing publication size."""
    entries = {}
    for path in sorted(output.rglob("*.json")):
        if path.name == "receipt-serialization.json":
            continue
        original = path.read_bytes()
        value = json.loads(original)
        published = (json.dumps(value, separators=(",", ":")) + "\n").encode()
        if json.loads(published) != value:
            raise ValueError("receipt serialization changed scientific values")
        path.write_bytes(published)
        entries[str(path.relative_to(output))] = dict(
            original_sha256=hashlib.sha256(original).hexdigest(),
            published_sha256=hashlib.sha256(published).hexdigest(),
        )
    write_json(
        output / "receipt-serialization.json",
        dict(
            scope=(
                "Whitespace-compacted publication copies; "
                "original receipts remain on local bulk storage"
            ),
            files=entries,
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    manifest, surfaces = {}, {}
    for scan in SCANS:
        root = args.data_root / scan
        data, bank, meta, _ = load_bundle(root / "bundle")
        phases, receipt = load_phase_bank(root / "bundle", bank)
        lookup = {int(n): i for i, n in enumerate(bank["norad"])}
        manifest[scan] = {}
        for study in STUDIES:
            source = root / study
            if not (source / "result.json").exists():
                continue
            result = json.loads((source / "result.json").read_text())
            rows = [json.loads(s) for s in (source / "evaluations.jsonl").read_text().splitlines()]
            if (
                result["input_digest"] != meta["input_sha256"]
                or result["orbit_digest"] != meta["orbit_bank_sha256"]
                or result["phase_receipt"] != receipt
                or result["evaluations"] != len(rows)
                or result["phase_model"] != "fixed-reception-frame-orbital-phase"
            ):
                raise ValueError("changed evidence or an actively running checkpoint")
            cfg = WrappedConfig(**result["config"])
            pool = np.asarray([lookup[n] for n in result["candidate_norad"]])
            max_error = 0.0
            for row in rows:
                provider = phase_provider(
                    phases,
                    bank,
                    data,
                    meta["site"],
                    (row["east_m"], row["north_m"]),
                    inertial_phase=True,
                )
                if row["arms"]["fitted-c"]["score"] + 1e-8 < row["arms"]["zero-c"]["score"]:
                    raise ValueError("nested zero-c feasible fit was lost")
                for arm in ("zero-c", "fitted-c"):
                    fit = row["arms"][arm]
                    active = np.asarray(fit["active"], int)
                    pred, opp, _, _ = provider.predict(
                        fit["phase_s"] + np.asarray(fit["satellite_phase_s"])[active], pool[active]
                    )
                    local = dict(fit, active=list(range(len(active))))
                    local["satellite_bias_hz"] = np.asarray(fit["satellite_bias_hz"])[active]
                    replay = replay_endpoint(data, bank["rf_hz"], pred, opp, local, cfg)
                    max_error = max(max_error, abs(replay["score"] - fit["score"]))
            target = args.output / scan / study
            target.mkdir(parents=True, exist_ok=True)
            digests = {}
            for name in ("result.json", "protocol.json", "evaluations.jsonl"):
                path = source / name
                if path.exists():
                    shutil.copyfile(path, target / name)
                    digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            summary = {a: diagnostic_summary(result, rows, a) for a in ("zero-c", "fitted-c")}
            manifest[scan][study] = dict(
                summary=summary,
                max_score_replay_error=max_error,
                source_files=digests,
                config=result["config"],
                candidate_count=len(pool),
                source_digests=result["source_digests"],
            )
            surfaces[scan, study] = rows
        starts = args.output / scan / "starts"
        starts.mkdir(parents=True, exist_ok=True)
        for path in (root / "bias-shape-starts-v1").glob("*.json"):
            shutil.copyfile(path, starts / path.name)
        for directory in root.glob("bias-shape-reciprocal*starts-v1"):
            shutil.copytree(directory, args.output / scan / directory.name, dirs_exist_ok=True)
        audits = []
        paths = [root / "bias-shape-reference-full-converged-v1" / "result.json"]
        paths.extend((root / "bias-shape-transport-full-audits-v1").glob("*/result.json"))
        paths.extend((root / "bias-shape-reciprocal-full-audits-v1").glob("*/result.json"))
        for path in paths:
            if not path.exists():
                continue
            audit = json.loads(path.read_text())
            if (
                not audit["completed"]
                or audit["input_digest"] != meta["input_sha256"]
                or audit["orbit_digest"] != meta["orbit_bank_sha256"]
                or audit["phase_receipt"] != receipt
            ):
                raise ValueError("completed full-catalogue audit with matching evidence required")
            destination = args.output / scan / "audits" / path.parent.relative_to(root)
            shutil.copytree(path.parent, destination, dirs_exist_ok=True)
            audits.append(
                dict(
                    source_directory=str(path.parent.relative_to(root)),
                    point=audit["point"],
                    candidate_count=len(audit["candidate_norad"]),
                    arms={
                        a: dict(
                            score=f["score"],
                            gain=f["score"] - f["known_conditional_score"],
                            satellites=f["norad"],
                        )
                        for a, f in audit["arms"].items()
                    },
                    source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
        manifest[scan]["full_catalogue_audits"] = audits
    write_json(args.output / "summary.json", manifest)
    convergence = args.data_root / "bias-shape-convergence-protocol.json"
    if convergence.exists():
        shutil.copyfile(convergence, args.output / "convergence-protocol.json")
    fig, axs = plt.subplots(2, 2, figsize=(12, 10), constrained_layout=True)
    for col, scan in enumerate(SCANS):
        rows = surfaces[scan, "bias-shape-transport-local-v1"]
        for ax, arm in zip(axs[:, col], ("zero-c", "fitted-c"), strict=True):
            ref = rows[0]["arms"][arm]["score"]
            plot = ax.scatter(
                [r["east_m"] / 1000 for r in rows],
                [r["north_m"] / 1000 for r in rows],
                c=[r["arms"][arm]["score"] - ref for r in rows],
                cmap="coolwarm",
                s=55,
            )
            ax.scatter([0], [0], marker="*", s=180, c="black", label="Configured reference")
            best = max(rows, key=lambda r: r["arms"][arm]["score"])
            ax.scatter(
                [best["east_m"] / 1000],
                [best["north_m"] / 1000],
                s=150,
                facecolors="none",
                edgecolors="black",
                label="Best sampled score",
            )
            ax.add_patch(plt.Circle((0, 0), 5, fill=False, color="gray"))
            ax.set(
                xlim=(-5.3, 5.3),
                ylim=(-5.3, 5.3),
                xlabel="East (km)",
                ylabel="North (km)",
                title=f"{scan[5:13]} / {arm} / {len(rows)} measured points",
            )
            ax.set_aspect("equal")
            fig.colorbar(plot, ax=ax, label="Penalized log score minus reference")
    fig.savefig(args.output / "transported-surfaces.png", dpi=160)
    plt.close(fig)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4), constrained_layout=True)
    scan = SCANS[0]
    base = surfaces[scan, "bias-shape-local-converged-v1"]
    moved = surfaces[scan, "bias-shape-transport-local-v1"]
    original = {(r["east_m"], r["north_m"]): r for r in base}
    matched = [
        (original[r["east_m"], r["north_m"]], r)
        for r in moved
        if (r["east_m"], r["north_m"]) in original
    ]
    for ax, arm in zip(axs, ("zero-c", "fitted-c"), strict=True):
        for idx, label in enumerate(("Untransported starts", "Transported starts")):
            ax.scatter(
                [pair[idx]["distance_m"] / 1000 for pair in matched],
                [pair[idx]["arms"][arm]["score"] for pair in matched],
                label=label,
            )
        ax.set(
            xlabel="Distance from reference (km)",
            ylabel="Penalized log score",
            title=f"Upper development / {arm}; matched locations and budgets",
        )
        ax.legend()
    fig.savefig(args.output / "initialization-comparison.png", dpi=160)
    plt.close(fig)
    rows = surfaces.get((SCANS[0], "bias-shape-reciprocal-local-v1"))
    if rows:
        fig, axs = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
        for ax, arm in zip(axs, ("zero-c", "fitted-c"), strict=True):
            reference = rows[0]["arms"][arm]["score"]
            plot = ax.scatter(
                [r["east_m"] / 1000 for r in rows],
                [r["north_m"] / 1000 for r in rows],
                c=[r["arms"][arm]["score"] - reference for r in rows],
                cmap="coolwarm",
                s=55,
            )
            ax.scatter([0], [0], marker="*", s=180, c="black")
            best = max(rows, key=lambda r: r["arms"][arm]["score"])
            ax.scatter(
                [best["east_m"] / 1000],
                [best["north_m"] / 1000],
                s=150,
                facecolors="none",
                edgecolors="black",
            )
            ax.add_patch(plt.Circle((0, 0), 5, fill=False, color="gray"))
            ax.set(
                xlim=(-5.3, 5.3),
                ylim=(-5.3, 5.3),
                xlabel="East (km)",
                ylabel="North (km)",
                title=f"Upper / {arm} / reciprocal starts / {len(rows)} points",
            )
            ax.set_aspect("equal")
            fig.colorbar(plot, ax=ax, label="Penalized log score minus reference")
        fig.savefig(args.output / "reciprocal-surfaces.png", dpi=160)
        plt.close(fig)
    compact_receipts(args.output)


if __name__ == "__main__":
    main()
