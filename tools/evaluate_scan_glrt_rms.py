#!/usr/bin/env python3
"""Paired, common-holdout RMS experiments on frozen scanner track membership."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def canonical_delta(delta, alias_spacing):
    """Express a GLRT frequency difference in the seed's known alias branch."""
    return np.asarray(delta) - np.rint(np.asarray(delta) / alias_spacing) * alias_spacing


def arrays(document: dict, members: list[str]) -> dict:
    source = {s["tracklet_id"]: s for s in document["series"]}
    rows = []
    for member in members:
        s = source[member]
        for t, y, obs in zip(s["t_s"], s["y_hz"], s["observations"], strict=True):
            rows.append(
                (
                    t,
                    y,
                    member,
                    obs["margin"],
                    obs["control_score"],
                    obs["candidate_rank"],
                    y
                    + 11.2e9
                    / s["actual_rf_hz"]
                    * canonical_delta(
                        obs["persisted"]["integer_tracking_cfo_hz"] - obs["measured_cfo_hz"],
                        1 / 4.4e-6,
                    ),
                )
            )
    rows.sort(key=lambda row: row[0])
    columns = zip(*rows, strict=True)
    return {
        name: np.array(column)
        for name, column in zip(
            ("t", "y", "segment", "margin", "control", "rank", "integer"), columns, strict=True
        )
    }


def chronological_split(t: np.ndarray, segment: np.ndarray) -> np.ndarray:
    training = np.zeros(len(t), bool)
    for name in np.unique(segment):
        idx = np.flatnonzero(segment == name)
        idx = idx[np.argsort(t[idx], kind="stable")]
        training[idx[: max(2, int(0.6 * len(idx)))]] = True
    return training


def fit(t, y, segment, training, degree=2, weight=None):
    if weight is None:
        weight = np.ones(len(t))
    names = np.unique(segment)
    if any(np.count_nonzero(training & (segment == name)) < 4 for name in names):
        raise ValueError("fewer than four training observations in a source segment")
    reference = float(np.mean(t[training]))
    scale = max(float(np.ptp(t[training])), 1.0)
    x = (t - reference) / scale
    design = np.column_stack(
        [*(segment == name for name in names), *(x**p for p in range(1, degree + 1))]
    )
    w = np.sqrt(weight[training])
    coef, _, rank, _ = np.linalg.lstsq(design[training] * w[:, None], y[training] * w, rcond=None)
    if rank < design.shape[1] or training.sum() <= design.shape[1]:
        raise ValueError("insufficient fit rank or degrees of freedom")
    return design @ coef


def rms(y):
    return float(np.sqrt(np.mean(np.square(y))))


def blocked_prediction(t, y, segment, retained, degree=3, quality=None, mode="equal"):
    """Five folds of whole 3-second blocks, shared across all receiver/edge paths."""
    fold = np.floor((t - t.min()) / 3).astype(int) % 5
    predicted = np.full(len(t), np.nan)
    for value in np.unique(fold):
        training = (fold != value) & retained
        weight = np.ones(len(t))
        if mode == "bounded":
            weight = np.clip(quality / np.median(quality[training]), 0.5, 2)
        elif mode == "production":
            weight = quality
        prediction = fit(t, y, segment, training, degree, weight)
        predicted[fold == value] = prediction[fold == value]
    if not np.all(np.isfinite(predicted)):
        raise ValueError("blocked prediction is incomplete")
    return predicted


def profiles():
    return (
        [{"name": "baseline", "gate": 0.025, "top_k": 8, "weight": "equal"}]
        + [
            {"name": f"margin_{gate:g}", "gate": gate, "top_k": 8, "weight": "equal"}
            for gate in (0.05, 0.075, 0.1, 0.15, 0.2)
        ]
        + [{"name": f"top_{k}", "gate": 0.025, "top_k": k, "weight": "equal"} for k in (1, 2, 4)]
        + [
            {"name": "bounded_score_weight", "gate": 0.025, "top_k": 8, "weight": "bounded"},
            {"name": "production_score_weight", "gate": 0.025, "top_k": 8, "weight": "production"},
            {"name": "integer_epoch", "gate": 0.025, "top_k": 8, "weight": "equal"},
        ]
    )


def score_profile(a, profile, degree=2):
    t, y, segment = a["t"], a["y"], a["segment"]
    training = chronological_split(t, segment)
    retained = (a["margin"] >= profile["gate"]) & (a["rank"] < profile["top_k"])
    fit_y = a["integer"] if profile["name"] == "integer_epoch" else y
    weight = np.ones(len(t))
    if profile["weight"] != "equal":
        q = np.minimum(a["margin"] / np.maximum(a["control"], 0.02), 16)
        weight = (
            np.clip(q / np.median(q[training]), 0.5, 2.0) if profile["weight"] == "bounded" else q
        )
    result = {
        "profile": profile["name"],
        "retention": float(retained.mean()),
        "training_retention": float(retained[training].mean()),
        "observations": len(t),
        "heldout_count": int((~training).sum()),
        "retained_count": int(retained.sum()),
    }
    try:
        prediction = fit(t, fit_y, segment, training & retained, degree, weight)
        full = fit(t, fit_y, segment, retained, degree, weight)
        result.update(
            status="ok",
            common_heldout_rms_hz=rms(y[~training] - prediction[~training]),
            own_heldout_rms_hz=rms(fit_y[~training] - prediction[~training]),
            retained_full_rms_hz=rms((fit_y - full)[retained]),
            common_full_rms_hz=rms(y - full),
            retained_span_s=float(np.ptp(t[retained])),
            maximum_retained_gap_s=max(
                float(np.max(np.diff(t[retained & (segment == s)]))) for s in np.unique(segment)
            ),
        )
        try:
            blocked = blocked_prediction(
                t,
                fit_y,
                segment,
                retained,
                degree,
                np.minimum(a["margin"] / np.maximum(a["control"], 0.02), 16),
                profile["weight"],
            )
            result["common_blocked_rms_hz"] = rms(y - blocked)
            result["blocked_status"] = "ok"
        except ValueError as error:
            result["blocked_status"] = str(error)
    except ValueError as error:
        result.update(status="insufficient_support", reason=str(error))
    return result


def bootstrap_scan_ratio(pairs, iterations=2000):
    # Average log improvement inside scan first; receivers/episodes are not independent trials.
    by_scan = defaultdict(list)
    for sid, candidate, baseline in pairs:
        by_scan[sid].append(np.log(candidate / baseline))
    values = np.array([np.mean(v) for v in by_scan.values()])
    if not len(values):
        return None
    rng = np.random.default_rng(20260910)
    estimates = np.exp(np.mean(rng.choice(values, (iterations, len(values))), axis=1))
    return {
        "scan_count": len(values),
        "geometric_rms_ratio": float(np.exp(np.mean(values))),
        "ratio_95pct": np.quantile(estimates, [0.025, 0.975]).tolist(),
    }


def summarize(rows, scans):
    baseline = {
        (r["session_id"], r["episode_id"]): r
        for r in rows
        if r["profile"] == "baseline" and r["status"] == "ok"
    }
    by_profile = defaultdict(list)
    for row in rows:
        by_profile[row["profile"]].append(row)
    summaries = []
    for name, group in by_profile.items():
        for rate in (2500000, 5000000, 0):
            for split in ("all", "development", "validation"):
                g = [
                    r
                    for r in group
                    if (rate == 0 or r["sample_rate_hz"] == rate)
                    and (split == "all" or scans[r["session_id"]] == split)
                ]
                if not g:
                    continue
                ok = [r for r in g if r["status"] == "ok"]
                pairs = [
                    (
                        r["session_id"],
                        r["common_heldout_rms_hz"],
                        baseline[r["session_id"], r["episode_id"]]["common_heldout_rms_hz"],
                    )
                    for r in ok
                    if (r["session_id"], r["episode_id"]) in baseline
                ]
                blocked = [r for r in ok if "common_blocked_rms_hz" in r]
                blocked_pairs = [
                    (
                        r["session_id"],
                        r["common_blocked_rms_hz"],
                        baseline[r["session_id"], r["episode_id"]]["common_blocked_rms_hz"],
                    )
                    for r in blocked
                    if "common_blocked_rms_hz"
                    in baseline.get((r["session_id"], r["episode_id"]), {})
                ]
                summaries.append(
                    {
                        "profile": name,
                        "sample_rate_hz": rate,
                        "split": split,
                        "eligible_episodes": len(g),
                        "fit_episodes": len(ok),
                        "median_retention": float(np.median([r["retention"] for r in g])),
                        "median_common_heldout_rms_hz": float(
                            np.median([r["common_heldout_rms_hz"] for r in ok])
                        )
                        if ok
                        else None,
                        "median_retained_full_rms_hz": float(
                            np.median([r["retained_full_rms_hz"] for r in ok])
                        )
                        if ok
                        else None,
                        "blocked_fit_episodes": len(blocked),
                        "median_common_blocked_rms_hz": float(
                            np.median([r["common_blocked_rms_hz"] for r in blocked])
                        )
                        if blocked
                        else None,
                        "paired_blocked": bootstrap_scan_ratio(blocked_pairs),
                        "paired": bootstrap_scan_ratio(pairs),
                    }
                )
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--degree", type=int, choices=(2, 3), default=3)
    args = parser.parse_args()
    root = args.output
    docs = [json.loads(p.read_text()) for p in (root / "evidence").glob("scan*.json")]
    docs.sort(key=lambda d: d["inventory"]["reference_utc_ns"])
    split = {
        d["inventory"]["session_id"]: "development" if i < len(docs) * 2 // 3 else "validation"
        for i, d in enumerate(docs)
    }
    rows, episodes, models, joined = [], [], [], []
    for doc in docs:
        inv = doc["inventory"]
        for ep in doc.get("episodes", []):
            span = ep["support_s"][1] - ep["support_s"][0]
            if span < 30:
                continue
            a = arrays(doc, ep["members"])
            meta = {
                "session_id": inv["session_id"],
                "episode_id": ep["episode_id"],
                "sample_rate_hz": inv["sample_rate_hz"],
                "span_s": span,
                "label": ep["label"],
                "segment_count": len(ep["members"]),
                "observations": len(a["t"]),
                "split": split[inv["session_id"]],
            }
            episodes.append(meta)
            for profile in profiles():
                rows.append({**meta, **score_profile(a, profile, args.degree)})
            for degree in (1, 2, 3):
                models.append({**meta, "degree": degree, **score_profile(a, profiles()[0], degree)})
        by_id = {ep["episode_id"]: ep for ep in doc.get("episodes", [])}
        for join in doc.get("joins", []):
            left, right = by_id[join["left_track_id"]], by_id[join["right_track_id"]]
            span = max(left["support_s"][1], right["support_s"][1]) - min(
                left["support_s"][0], right["support_s"][0]
            )
            if span < 60:
                continue
            a = arrays(doc, left["members"] + right["members"])
            joined.append(
                {
                    "session_id": inv["session_id"],
                    "span_s": span,
                    "join": join,
                    **score_profile(a, profiles()[0], args.degree),
                }
            )
    result = {
        "cohort_scans": len(docs),
        "long_definition_s": 30,
        "fit_model": (
            f"degree {args.degree} in scaled time plus one constant per frozen source tracklet"
        ),
        "heldout": "last 40 percent per source tracklet; baseline support fixed for all profiles",
        "limitation": (
            "Track discovery and merge selection used the entire recording; "
            "conditional retrospective errors, not blind end-to-end validation."
        ),
        "profiles": profiles(),
        "episodes": episodes,
        "rows": rows,
        "summaries": summarize(rows, split),
        "polynomial_models": models,
        "long_join_candidates": joined,
        "scan_split": split,
    }
    write_json(root / "rms-study.json", result)
    if rows:
        fields = sorted(set().union(*(r.keys() for r in rows)))
        with (root / "rms-study.csv").open("w") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8))
    for rate, color in ((2500000, "#167d9a"), (5000000, "#bf5b32")):
        s = [r for r in result["summaries"] if r["sample_rate_hz"] == rate and r["split"] == "all"]
        gates = [r for r in s if r["profile"] == "baseline" or r["profile"].startswith("margin_")]
        x = [
            0.025 if r["profile"] == "baseline" else float(r["profile"].split("_")[1])
            for r in gates
        ]
        for ax, key in zip(
            axes[:2], ("median_retained_full_rms_hz", "median_common_heldout_rms_hz"), strict=True
        ):
            ax.plot(x, [r[key] for r in gates], "o-", label=f"{rate / 1e6:g} Msps", color=color)
        axes[2].plot(
            x,
            [r["median_retention"] * 100 for r in gates],
            "o-",
            color=color,
            label=f"{rate / 1e6:g} Msps",
        )
    for ax, title in zip(
        axes,
        ("RMS on retained points", "RMS on fixed later observations", "Observation retention"),
        strict=True,
    ):
        ax.set_title(title)
        ax.set_xlabel("GLRT margin threshold")
        ax.grid(alpha=0.2)
        ax.legend()
    axes[0].set_ylabel(f"Median degree-{args.degree} fit RMS (Hz)")
    axes[1].set_ylabel("Median conditional held-out RMS (Hz)")
    axes[2].set_ylabel("Percent of baseline observations")
    fig.suptitle("67 scans: threshold gains must be assessed alongside coverage")
    fig.tight_layout()
    fig.savefig(root / "threshold-rms.png", dpi=160)
    plt.close(fig)
    print(f"{len(docs)} scans; {len(episodes)} episodes >=30s; {len(joined)} proposed joins >=60s")
    for r in result["summaries"]:
        if r["sample_rate_hz"] == 0 and r["split"] == "all":
            print(r)


if __name__ == "__main__":
    main()
