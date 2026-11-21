"""Score the DS30 predictions after locking every receiver's output."""

from collections import Counter
from pathlib import Path
from statistics import median

from ..scoring import ARMS, distribution
from . import blind_compact_score
from .blind_compact_roster import METHODS, seal
from .compact_position_diagnosis import HZ, ident, same
from .ds30_panel import DATA, DS29, OUT, WORK, snapshot_tools
from .full_v5_check import _sha
from .reverse_glrt_report import read, write_csv


def summary(rows, references):
    result = []
    for name in ARMS:
        for method in METHODS:
            sample = [r for r in rows if r["calibration"] == name and r["method"] == method]
            scored = [r for r in sample if r["error_km"] is not None]
            errors = distribution(r["error_km"] for r in scored)
            rms = distribution(r["conditional_rf_rms_hz"] for r in sample)
            timing = distribution(r["end_to_end_wall_s"] for r in sample)
            result.append(
                dict(
                    method=method,
                    calibration=name,
                    assigned=len(sample),
                    reference_eligible=sum(references[r["case"]] is not None for r in sample),
                    fixes=sum(r["fix"] for r in sample),
                    scored_fixes=len(scored),
                    median_km=errors["p50"],
                    p95_km=errors["p95"],
                    maximum_km=errors["max"],
                    within_1km=sum(r["error_km"] <= 1 for r in scored),
                    within_2km=sum(r["error_km"] <= 2 for r in scored),
                    median_conditional_rf_rms_hz=rms["p50"],
                    rf_rms_count=rms["n"],
                    median_wall_s=timing["p50"],
                    p95_wall_s=timing["p95"],
                    fixes_within_recorded_span=sum(
                        r["fix"] and r["end_to_end_wall_s"] <= r["recorded_span_s"] for r in sample
                    ),
                    median_detector_cpu_s=median(r["detector_cpu_s"] for r in sample),
                    median_solver_wall_s=median(r["solver_wall_s"] for r in sample),
                )
            )
    return result


def paired_results(rows):
    lookup = {(r["case"], r["calibration"], r["method"]): r for r in rows}
    pairs = []
    for r in rows:
        if r["method"] == "original":
            continue
        base = lookup[r["case"], r["calibration"], "original"]
        delta = None
        if r["error_km"] is not None and base["error_km"] is not None:
            delta = r["error_km"] - base["error_km"]
        pairs.append(
            dict(
                case=r["case"],
                method=r["method"],
                calibration=r["calibration"],
                difference_km=delta,
                speedup=base["end_to_end_wall_s"] / r["end_to_end_wall_s"],
            )
        )
    return pairs


def factor_agreement(original, candidate):
    """Compare strongest accepted factors at identical physical receiver opportunities."""
    shared, original_only, candidate_only, switched = [], 0, 0, 0
    for a, b in zip(original, candidate, strict=True):
        if ident(a) != ident(b) or a["actual_rf_hz"] != b["actual_rf_hz"]:
            raise ValueError("receiver opportunities differ")
        x, y = blind_compact_score.strongest(a), blind_compact_score.strongest(b)
        if same(x, y):
            shared.append(y[HZ] - x[HZ])
        elif x is not None and y is not None:
            switched += 1
        elif x is not None:
            original_only += 1
        elif y is not None:
            candidate_only += 1
    return dict(
        opportunities=len(original),
        original_only=original_only,
        alternative_only=candidate_only,
        matched_winners=len(shared),
        both_accepted_different_winners=switched,
        matched_median_signed_cfo_delta_hz=median(shared) if shared else None,
        matched_median_abs_cfo_delta_hz=median(map(abs, shared)) if shared else None,
    )


def figures(rows, references):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.ticker import PercentFormatter

    from .blind_compact_figures import COLORS, LINES, NAMES, cumulative

    for kind, title, panels, xlabel in [
        (
            "position-error",
            "Horizontal position error on DS30",
            [("fitted_c", "Fitted RF calibration"), ("c0", "RF calibration fixed at zero")],
            "Horizontal position error (km)",
        ),
        (
            "runtime",
            "Gauss runtime on the same DS30 recordings",
            [
                ("end_to_end_wall_s", "I/Q through position, including orbit retries"),
                ("detector_cpu_s", "Detector CPU time"),
            ],
            "Time per recording (minutes)",
        ),
    ]:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.9), sharey=True)
        for ax, (field, caption) in zip(axes, panels, strict=True):
            curves = {}
            for m in METHODS:
                if kind == "position-error":
                    sample = [
                        r
                        for r in rows
                        if r["method"] == m
                        and r["calibration"] == field
                        and references[r["case"]] is not None
                    ]
                    vals = [r["error_km"] for r in sample]
                else:
                    sample = [
                        r for r in rows if r["method"] == m and r["calibration"] == "fitted_c"
                    ]
                    vals = [r[field] / 60 for r in sample]
                curves[m] = (vals, len(sample))
            xmax = max((v for vals, _ in curves.values() for v in vals if v is not None), default=1)
            limits = (0, max(1, xmax * 1.08))
            for m, (vals, n) in curves.items():
                if n:
                    x, y = cumulative(vals, n, limits)
                    ax.step(
                        x,
                        y,
                        where="post",
                        color=COLORS[m],
                        linestyle=LINES[m],
                        lw=2.3,
                        label=NAMES[m],
                    )
                    finite = sorted(v for v in vals if v is not None)
                    ax.scatter(
                        finite,
                        [(i + 1) / n for i in range(len(finite))],
                        s=16,
                        color=COLORS[m],
                        zorder=3,
                    )
            ax.set(xlim=limits, ylim=(-0.025, 1.04), title=caption, xlabel=xlabel)
            ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1])
            ax.spines[["right", "top"]].set_visible(False)
            ax.grid(color="#dce2e4", lw=0.8)
            ax.set_axisbelow(True)
        axes[0].set_ylabel(
            "Fraction of reference-eligible recordings"
            if kind == "position-error"
            else "Fraction of recordings"
        )
        fig.suptitle(title, x=0.055, ha="left", y=0.985, fontsize=19, fontweight="bold")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(
            handles, labels, ncol=3, frameon=False, loc="upper left", bbox_to_anchor=(0.051, 0.914)
        )
        fig.subplots_adjust(top=0.72, bottom=0.17, left=0.085, right=0.977, wspace=0.17)
        fig.savefig(OUT / (kind + ".png"), dpi=170, facecolor="white")
        plt.close(fig)


def score():
    methods, predictions = blind_compact_score.inventory(OUT, WORK)
    # Read the separately installed station authority only after the prediction lock exists.
    authority_path = Path("/etc/leo/station-authority/gauss-r20-lt3d-004b-20261001-v1.json")
    if _sha(authority_path) != _sha(DS29 / "site-authority.json"):
        raise ValueError("station authority differs from the comparison reference")
    authority = read(authority_path)
    manifest = read(DATA / "manifest.json")
    raw = {m["dataset_label"]: m for m in manifest["members"]}
    audit = [
        snapshot_tools().site_audit(raw[r["case"]["id"]], authority)
        for r in read(OUT / "roster.json")["cases"]
    ]
    references = {
        r["dataset_label"]: (
            [r["reference"]["latitude_deg"], r["reference"]["longitude_deg"]]
            if r["reference"]
            else None
        )
        for r in audit
    }
    seal(
        OUT / "reference-audit.json",
        dict(
            prediction_lock_sha256=_sha(OUT / "prediction-lock.json"),
            authority_sha256=_sha(authority_path),
            authority_revision=authority["revision"],
            cases=audit,
        ),
    )
    parity = blind_compact_score.original_replay_parity(methods, OUT)
    span = {r["case"]: r["hardware_span_s"] for r in parity}
    rows = blind_compact_score.join_survey(methods, predictions, references)
    for r in rows:
        r["recorded_span_s"] = span[r["case"]]
        metrics = predictions[r["case"], r["method"]]["metrics"]
        r["native_observations"] = metrics.get("observations", metrics.get("native_observations"))
        r["tracks"] = metrics.get("tracks")
        r["stock_status"] = metrics["stock_status"]
        r["stock_reason"] = metrics["stock_reason"]
        repair = r["applied_orbit_policy"] = metrics["applied_orbit_policy"]
        if repair != "stock":
            folder = Path(methods[r["case"], r["method"]]["prediction_path"]).parent
            expected = read(folder / "binding.json")
            expected["job"]["output_root"] = str(folder / repair)
            if read(folder / repair / "request.json") != expected:
                raise ValueError("repair changed scientific input")
    write_csv(OUT / "recordings.csv", rows)
    write_csv(OUT / "summary.csv", summary(rows, references))
    write_csv(OUT / "paired.csv", paired_results(rows))
    agreement = []

    def probes(label, method):
        path = Path(methods[label, method]["prediction_path"]).with_name("native.json")
        return read(path)["source"]["probes"]

    for label in references:
        original = probes(label, "original")
        for method in ("checked", "cancellation"):
            agreement.append(
                dict(case=label, method=method, **factor_agreement(original, probes(label, method)))
            )
    write_csv(OUT / "factor-agreement.csv", agreement)
    write_csv(OUT / "original-replay-parity.csv", parity)
    figures(rows, references)
    print(
        "Verified",
        len(methods),
        "runs;",
        Counter(r["applied_orbit_policy"] for r in rows if r["calibration"] == "fitted_c"),
        flush=True,
    )


if __name__ == "__main__":
    score()
