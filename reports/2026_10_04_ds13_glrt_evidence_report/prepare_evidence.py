"""Snapshot existing DS13 experiments; no RF collection or solver rerun.

Requires NumPy and Matplotlib on the analysis host. The portable report itself
is rebuilt with build_report.py using only the Python standard library.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ALIAS = 1 / 4.4e-6
FIGURES = {
    "all-candidates": "full-scan-A-refinement/within-probe-300hz/all.png",
    "refinement-case": "66204-candidate-guided-refinement/before-after.png",
    "pair-distribution": "full-scan-A-refinement/after-refinement-pair-distribution.png",
    "margin-cutoffs": "full-scan-A-refinement/pair-distribution-margin-cutoffs.png",
    "margin-06": "full-scan-A-refinement/pair-distribution-margin-0p6.png",
    "khz-pairs": "full-scan-A-refinement/khz-pair-audit/frequency-and-epoch-separation.png",
    "exclusivity": "full-scan-A-refinement/solver/66204-exclusivity-explained.png",
    "timing-fix": "absolute-timing-penalty10/58622-selected-timing-regression.png",
    "refined-coverage": "full-scan-A-refinement/solver/coverage-comparison.png",
    "refined-unassigned": "full-scan-A-refinement/solver/fitted-c-unassigned.png",
    "top-coverage": "full-scan-A-refinement/top-one/top-candidate-window-coverage.png",
    "top-fit": "full-scan-A-refinement/top-one/fitted-c-assignments.png",
    "top-zero": "full-scan-A-refinement/top-one/zero-c-assignments.png",
    "scan-b-unassigned": "absolute-timing-penalty10/B-fitted-c-unassigned.png",
}
RECEIPTS = {
    "top-audit": "full-scan-A-refinement/top-one/audit.json",
    "refined-audit": "full-scan-A-refinement/solver/audit.json",
    "timing-audit": "absolute-timing-penalty10/audit.json",
    "target-refinement": "66204-candidate-guided-refinement/results.json",
    "exclusivity": "full-scan-A-refinement/solver/66204-exclusivity-example.json",
    "khz-pairs": "full-scan-A-refinement/khz-pair-audit/audit.json",
    "pair-distribution": "full-scan-A-refinement/after-refinement-pair-distribution.json",
    "margin-cutoffs": "full-scan-A-refinement/pair-distribution-margin-cutoffs.json",
    "margin-06": "full-scan-A-refinement/pair-distribution-margin-0p6.json",
    "top-coverage": "full-scan-A-refinement/top-one/top-candidate-window-coverage.json",
}
SCRIPTS = [
    "candidate_guided_refinement.py", "refine_full_scan_A.py",
    "run_candidate_guided_refinement.py", "absolute_timing_solver.py",
    "greedy_pool_two_scans.py", "greedy_restart_scan.py",
    "penalty_replace_search.py", "solve_refined_scan_A.py", "top_one_scan_A.py",
    "audit_absolute_timing_solver.py", "audit_refined_scan_A.py",
    "plot_refined_66204_exclusivity.py", "investigate_khz_pairs.py",
    "plot_refined_pair_distribution.py", "plot_pair_margin_cutoffs.py",
    "plot_pair_margin_06.py", "plot_close_candidate_scan.py",
    "plot_top_candidate_window_coverage.py", "test_candidate_guided_refinement.py",
    "test_top_one_scan_A.py", "test_absolute_timing_solver.py",
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(bulk, frozen, scorer_source):
    assets = HERE / "assets"
    evidence = HERE / "evidence"
    for d in (assets, evidence, HERE / "sources"):
        d.mkdir(parents=True, exist_ok=True)
    manifest = []

    def record(source, target=None, kind="source"):
        item = dict(source=str(source), sha256=sha(source), bytes=source.stat().st_size, kind=kind)
        if target:
            item.update(packaged=str(target.relative_to(HERE)), packaged_sha256=sha(target))
        manifest.append(item)

    for name, source in FIGURES.items():
        src, dst = bulk / source, assets / f"{name}.png"
        shutil.copyfile(src, dst)
        record(src, dst, "saved figure")
    for name, source in RECEIPTS.items():
        src, dst = bulk / source, evidence / f"{name}.json.gz"
        dst.write_bytes(gzip.compress(src.read_bytes(), mtime=0))
        record(src, dst, "saved receipt; lossless gzip")
    for name in SCRIPTS:
        src, dst = bulk / name, HERE / "sources" / name
        shutil.copyfile(src, dst)
        record(src, dst, "forensic source snapshot")
    dst = HERE / "sources/installed_pilot_methods.py"
    shutil.copyfile(scorer_source, dst)
    record(scorer_source, dst, "installed refinement scorer; not a runtime dependency of the report")
    research = frozen.parents[2]
    metadata = dict(scans=[])
    for label, session in [("A", "scan-fw-911c4e5db9243281"), ("B", "scan-fw-ffa1cc19d8d7c09f")]:
        src = research / "2026_10_02_ds13_timing_em/scans" / session / "bundle.json"
        bundle = json.loads(src.read_text())
        metadata["scans"].append(dict(scan=label, session_id=session, origin_utc_ns=bundle["origin_utc_ns"],
            capture_start_utc=datetime.fromtimestamp(bundle["origin_utc_ns"]/1e9, timezone.utc).isoformat(),
            input_manifest_sha256=bundle["provenance"]["input_manifest_sha256"], bundle_sha256=sha(src)))
        record(src, kind="scan metadata; selected fields in detector-provenance.json")
        if label == "A":
            metadata["boundary_example"] = [dict(row_index=i, **bundle["alias_grouping"]["representative_rows"][i]) for i in (7169,562,4590)]
    src = research / "2026_10_02_ds13_from_911c4e5d/local/analysis/scan-fw-911c4e5db9243281.json"
    metadata["scan_A_configuration"] = json.loads(src.read_text())["glrt"]["configuration"]
    record(src, kind="acquisition configuration; selected fields in detector-provenance.json")
    (evidence / "detector-provenance.json").write_text(json.dumps(metadata,indent=2)+"\n")

    results, summaries, pool_metrics = {}, [], []
    for stage, scan, prefix in [
        ("original", "A", "absolute-timing-penalty10/A-"),
        ("original", "B", "absolute-timing-penalty10/B-"),
        ("refined", "A", "full-scan-A-refinement/solver/A-"),
        ("top", "A", "full-scan-A-refinement/top-one/"),
    ]:
        for arm in ("fitted-c", "zero-c"):
            src = bulk / f"{prefix}{arm}.json"
            data = json.loads(src.read_text())
            key = f"{scan}-{stage}-{arm}"
            results[key] = data
            dst = evidence / f"{key}.json.gz"
            dst.write_bytes(gzip.compress(src.read_bytes(), mtime=0))
            record(src, dst, "solver receipt; lossless gzip")
            f = data["final"]
            summaries.append(dict(key=key, stage=stage, scan=scan, arm=arm,
                denominator=data["denominator"], assigned=f["assigned"], unassigned=f["unassigned"],
                satellites=f["satellites"], objective=f["objective"], coverage=f["coverage"],
                assigned_rms_hz=float(np.sqrt(np.mean([a["residual_hz"]**2 for a in f["assignments"]]))),
                greedy_assigned=data["initial"]["assigned"],
                replacement_trials=len(data["trials"]), accepted=sum(t["accepted"] for t in data["trials"]),
                elapsed_s=data["elapsed_s"], converged=data["converged"]))
    for key, source in [
        ("A-original", "absolute-timing-penalty10/scan-A/candidate-pool.json"),
        ("B-original", "absolute-timing-penalty10/scan-B/candidate-pool.json"),
        ("A-refined", "full-scan-A-refinement/solver/scan-A/candidate-pool.json"),
        ("A-top", "full-scan-A-refinement/top-one/candidate-pool.json"),
    ]:
        src = bulk / source
        p = json.loads(src.read_text())
        arms = p["arms"]
        modes = lambda arm: [(m["catalog_number"], m["offset_s"]) for m in arms[arm]]
        assert modes("fitted-c") == modes("zero-c")
        pool_metrics.append(dict(key=key, catalog_ids=len(p["inventory"]),
            matched_modes=len(arms["fitted-c"]), discovery_s=p["elapsed_s"],
            source_sha256=sha(src), source_inputs=p["sources"]))
        record(src, kind="large candidate pool; hash only, not bundled")

    src = bulk / "full-scan-A-refinement/refined.json"
    refined = json.loads(src.read_text())
    record(src, kind="full refinement trace; compact measurements bundled separately")
    record(frozen, kind="frozen observations; compact measurements bundled separately")
    rows = sorted(refined["records"], key=lambda r: r["row_index"])
    groups = {}
    for r in rows:
        groups.setdefault(tuple(r["probe_key"]), []).append(r)
    margin = lambda r: r["refinement"].get("margin", r["original_margin"])
    winners = {max(rs, key=lambda r: (margin(r), -r["row_index"]))["row_index"] for rs in groups.values()}
    assert len(winners) == 3837
    multiplicities = Counter(map(len, groups.values()))
    owners = {k: {a["row_index"]: a["catalog_number"] for a in v["final"]["assignments"]}
              for k, v in results.items() if k.startswith("A-")}
    with np.load(frozen) as obs:
        stream = io.StringIO(newline="")
        fields = ["row_index", "time_s", "receiver", "channel", "group", "original_hz", "refined_hz",
                  "original_margin", "refined_margin", "status", "top_candidate"] + sorted(owners)
        w = csv.DictWriter(stream, fieldnames=fields)
        w.writeheader()
        for r in rows:
            i = r["row_index"]
            item = dict(row_index=i, time_s=float(obs["times_s"][i]), receiver=int(obs["receiver"][i]),
                channel=int(obs["channel"][i]), group=int(obs["group"][i]), original_hz=r["original_hz"],
                refined_hz=r["output_hz"], original_margin=r["original_margin"], refined_margin=margin(r),
                status=r["refinement"]["status"], top_candidate=int(i in winners))
            item.update({k: v.get(i, "") for k, v in owners.items()})
            w.writerow(item)
    (evidence / "scan-A-candidates.csv.gz").write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
    metrics = dict(results=summaries, pools=pool_metrics,
        multiplicity={str(k): v for k, v in sorted(multiplicities.items())},
        refinement=dict(count=len(rows), windows=len(groups),
            improved=sum(margin(r) > r["original_margin"] for r in rows),
            failed=sum(r["refinement"]["status"] != "refined" for r in rows),
            elapsed_s=refined["elapsed_s"], workers=refined["workers"]),
        scope="Saved, in-sample development results at the known position. No new solver run.")
    (evidence / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    audit = json.loads((bulk / RECEIPTS["refined-audit"]).read_text())
    make_figures(rows, multiplicities, results, assets, audit)
    for dst in sorted(assets.glob("*.png")):
        if dst.stem not in FIGURES:
            manifest.append(dict(packaged=str(dst.relative_to(HERE)), packaged_sha256=sha(dst),
                kind="derived figure; prepare_evidence.py, measurements and solver receipts"))
    for name in ("metrics.json", "scan-A-candidates.csv.gz", "detector-provenance.json"):
        dst = evidence / name
        manifest.append(dict(packaged=str(dst.relative_to(HERE)), packaged_sha256=sha(dst), kind="derived evidence"))
    (evidence / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def make_figures(rows, multiplicities, results, assets, audit):
    plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
    blue, orange = "#0072b2", "#d55e00"
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = sorted(multiplicities)
    bars = ax.bar(x, [multiplicities[n] for n in x], color=blue)
    ax.bar_label(bars, padding=4)
    ax.set(xlabel="Retained candidates in one RX/channel/20 ms window", ylabel="Windows", xticks=x,
           title="Scan A: 7,382 candidates in 3,837 windows")
    ax.margins(y=.15)
    fig.tight_layout(); fig.savefig(assets / "multiplicity.png", dpi=160); plt.close(fig)

    delta = [r["refinement"].get("margin", r["original_margin"]) - r["original_margin"] for r in rows]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3))
    axes[0].hist(delta, bins=65, color=blue)
    axes[0].set(xlabel="Refined margin − original margin", ylabel="Candidates", yscale="log",
                title="Signal-score change (all 7,382 candidates)")
    axes[0].axvline(0, c="black", lw=1)
    for i, stats in enumerate(audit["arms"]):
        arm = stats["arm"]
        before = stats["fixed_old_membership_rms_before"]
        after = stats["fixed_old_membership_rms_after"]
        axes[1].plot([0, 1], [before, after], "o-", label=arm, c=[blue, orange][i])
        for xx, yy in enumerate([before, after]):
            axes[1].annotate(f"{yy:.1f}", (xx, yy), xytext=(8, 0), textcoords="offset points")
    axes[1].set(xticks=[0, 1], xticklabels=["Original", "Refined"], xlim=(-.15, 1.4),
                ylabel="Orbit residual RMS (Hz)", title="Fixed old memberships and predictions")
    axes[1].legend(); fig.tight_layout(); fig.savefig(assets / "refinement-tradeoff.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7))
    for arm, color in [("fitted-c", blue), ("zero-c", orange)]:
        d = results[f"A-top-{arm}"]
        trace = d["initial_trace"]
        axes[0].plot(range(1, len(trace)+1), [t["objective"] for t in trace], "o-", ms=3, c=color, label=arm)
        losses = sorted(t["trial_score"]-t["before_score"] for t in d["trials"])
        axes[1].plot(range(1,len(losses)+1), losses, "o-", ms=3, c=color, label=arm)
    axes[0].set(xlabel="Satellites selected", ylabel="Assigned windows − 10 × satellites", title="Greedy construction: Scan A, top candidates")
    axes[1].set(xlabel="Removal trial (sorted within each arm)", ylabel="Trial objective − current objective", title="One-out / greedy-many-in: no accepted changes")
    axes[1].axhline(0, c="black", ls="--", lw=1)
    for ax in axes: ax.legend(); ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(assets / "solver-progress.png", dpi=160); plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(12, 9))
    for ax, arm, color in zip(axes, ("fitted-c", "zero-c"), (blue, orange)):
        selected = sorted(results[f"A-top-{arm}"]["final"]["selected"], key=lambda r: -r["count"])
        ax.bar(range(len(selected)), [s["count"] for s in selected], color=color)
        ax.set(xticks=range(len(selected)), xticklabels=[str(s["catalog_number"]) for s in selected],
               ylabel="Assigned top-candidate windows", title=f"Scan A · {arm} · 33 selected satellites")
        ax.tick_params(axis="x", rotation=90)
    fig.tight_layout(); fig.savefig(assets / "satellite-support.png", dpi=160); plt.close(fig)

    # Reconstruct the saved model values; no refit or extrapolation.
    raw = list(csv.DictReader(io.StringIO(gzip.decompress((HERE / "evidence/scan-A-candidates.csv.gz").read_bytes()).decode())))
    lookup = {int(r["row_index"]): r for r in raw}
    owned = results["A-top-fitted-c"]["final"]["assignments"]
    assigned_ids = {a["row_index"] for a in owned}
    numbers = sorted({a["catalog_number"] for a in owned})
    cmap = plt.get_cmap("turbo")
    colors = {n:cmap(i/max(1,len(numbers)-1)) for i,n in enumerate(numbers)}
    wrap = lambda f: (f+ALIAS/2)%ALIAS-ALIAS/2
    fig, axes = plt.subplots(4,2,figsize=(15,15),sharex=True,sharey=True)
    for rx in (0,1):
        for ch in (1,2,3,4):
            ax = axes[ch-1,rx]
            lane = lambda r: int(r["receiver"])==rx and int(r["channel"])==ch
            un = [r for r in raw if int(r["top_candidate"]) and lane(r) and int(r["row_index"]) not in assigned_ids]
            ax.scatter([float(r["time_s"]) for r in un], [wrap(float(r["refined_hz"]))/1000 for r in un], s=13,c="#888888",zorder=3)
            for n in numbers:
                aa = sorted([a for a in owned if a["catalog_number"]==n and lane(lookup[a["row_index"]])],key=lambda a:float(lookup[a["row_index"]]["time_s"]))
                if not aa: continue
                t = np.array([float(lookup[a["row_index"]]["time_s"]) for a in aa])
                y = np.array([float(lookup[a["row_index"]]["refined_hz"]) for a in aa])
                pred = wrap(y-np.array([a["residual_hz"] for a in aa]))/1000
                cuts = np.flatnonzero((np.diff(t)>5)|(abs(np.diff(pred))>100))+1
                for part in np.split(np.arange(len(t)),cuts):
                    ax.plot(t[part],pred[part],c=colors[n],lw=1.2,alpha=.85)
                ax.scatter(t,wrap(y)/1000,c=[colors[n]],s=8,zorder=4)
            ax.set(title=f"RX{rx} · CH{ch}",xlim=(0,300),ylim=(-114,114))
            ax.grid(alpha=.15)
            if rx==0: ax.set_ylabel("Wrapped measured CFO (kHz)")
            if ch==4: ax.set_xlabel("Receive time (s)")
    from matplotlib.lines import Line2D
    handles=[Line2D([0],[0],color=colors[n],marker=".",label=str(n)) for n in numbers]
    handles.append(Line2D([0],[0],color="#888888",marker=".",ls="none",label="Unassigned"))
    fig.legend(handles=handles,ncol=9,loc="lower center",bbox_to_anchor=(.5,.025),fontsize=9)
    fig.suptitle("Scan A · top GLRT response · fitted c · 3,644 / 3,837 windows assigned\nColored dots: assigned GLRT · lines: saved orbit + calibration at assigned times · gray: unassigned",fontsize=15)
    fig.text(.5,.012,"No extrapolation: line segments connect saved predictions only within assigned support; breaks at >5 s gaps and alias wraps.",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.125,1,.94));fig.savefig(assets / "top-orbits.png",dpi=150);plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk", type=Path, required=True)
    parser.add_argument("--frozen", type=Path, required=True)
    parser.add_argument("--scorer-source", type=Path, required=True)
    args = parser.parse_args()
    snapshot(args.bulk, args.frozen, args.scorer_source)
