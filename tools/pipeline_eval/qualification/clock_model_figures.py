"""Prepare standard position figures from the sealed receiver-clock studies."""

import argparse
import json

from ..__main__ import read_predictions, write
from . import native_clock_donor
from .clock_model_trial import METHODS, REPORT, _gzip
from .full_v5_check import _sha
from .projector_roof import roster
from .recording_to_v5 import save


def prepare():
    verify = native_clock_donor.iq.verify_lock
    verified = {case: verify(REPORT / case) for case in ("timing", "confirmation", "wrong_offer")}
    cohort_locks = {
        cohort: json.loads((REPORT / cohort / "prediction-lock.json").read_bytes())
        for cohort in verified
    }
    inside = ("timing", "confirmation")
    cases = [ident for cohort in inside for ident in cohort_locks[cohort]["cases"]]
    methods = (*METHODS[:3], "robust_orbit_fit")
    rows = []
    for method in methods:
        for cohort in inside:
            rows.extend(read_predictions(REPORT / cohort / f"{method}.jsonl.gz").values())
    primary = "matched-figure-positions.jsonl.gz"
    _gzip(REPORT / primary, rows)
    root = json.loads((REPORT / "prediction-lock.json").read_bytes())
    save(REPORT / "matched-figure-lock.json", dict(
        cases=cases, files={primary: _sha(REPORT / primary)},
        source_lock_sha256=root["source_lock_sha256"], cohort_locks=verified,
    ))

    refs = {ref["id"]: ref for ref in roster()}
    rows, queries = [], []
    for method in METHODS[:3]:
        rows.extend(
            read_predictions(REPORT / "wrong_offer" / f"{method}.jsonl.gz").values()
        )
    for row in rows:
        if row["variant"] != METHODS[0]:
            continue
        record = row["recording"]
        keys = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256")
        queries.append(dict(
            id=row["id"], condition="correct tile omitted", recording=record,
            truth=refs[record]["truth"], bindings={key: row[key] for key in keys},
        ))
    pos, qname = "wrong-figure-positions.jsonl.gz", "wrong-figure-queries.json"
    _gzip(REPORT / pos, rows)
    save(REPORT / qname, dict(queries=queries))
    save(REPORT / "wrong-figure-lock.json", dict(
        cases=cohort_locks["wrong_offer"]["cases"],
        files={name: _sha(REPORT / name) for name in (pos, qname)},
        source_lock_sha256=root["source_lock_sha256"],
        cohort_lock_sha256=verified["wrong_offer"],
    ))

    donor = native_clock_donor.REPORT
    primary_lock = verify(donor)
    historic_lock = verify(donor / "archived-controls")
    original = json.loads((donor / "prediction-lock.json").read_bytes())
    compact = "ordinary_v5_secant_fit.jsonl.gz"
    write(donor / compact, (donor / "archived-controls" / compact).read_bytes())
    save(donor / "figure-lock.json", dict(
        cases=original["cases"], plan_sha256=original["plan_sha256"],
        files=dict(original["files"], **{compact: _sha(donor / compact)}),
        archive_lock_sha256=historic_lock, receiver_lock_sha256=primary_lock,
    ))


def custom():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    real = json.loads((REPORT / "scores.json").read_bytes())
    donor = json.loads((native_clock_donor.REPORT / "scores.json").read_bytes())
    cohorts = (
        ("Timing", [r for r in real if r["cohort"] == "timing"], METHODS[:2]),
        ("Confirmation", [r for r in real if r["cohort"] == "confirmation"], METHODS[:2]),
        ("Ordinary factors", donor, native_clock_donor.METHODS[:2]),
    )
    positions, labels, marks, separators = [], [], [], []
    y = 0
    metrics = ("error_km", "rf_rms_hz", "held_rms_hz")
    for label, rows, (clock, fixed) in cohorts:
        keyed = {(r["id"], r["variant"], r["arm"]): r for r in rows}
        for ident in sorted({r["id"] for r in rows}):
            pair = []
            for arm in ("c0", "fitted_c"):
                after, before = keyed[ident, clock, arm], keyed[ident, fixed, arm]
                pair.append([
                    after[k] - before[k] if after[k] is not None and before[k] is not None else None
                    for k in metrics
                ])
            positions.append(y)
            labels.append(f"{label}  ·  {ident}")
            marks.append(pair)
            y += 1
        separators.append(y - 0.5)
        y += 1

    fig, axes = plt.subplots(ncols=3, sharey=True, figsize=(12.5, 6.3), layout="constrained")
    for i, (ax, title) in enumerate(zip(
        axes, ("Geographic error (km)", "Fit RF RMS (Hz)", "Held RF RMS (Hz)"), strict=True
    )):
        ax.axvline(0, color="#82909b", linewidth=0.9)
        for j, (mark, color, caption) in enumerate((
            ("o", "#137a83", "c = 0"),
            ("D", "#b65b2f", "Fitted c"),
        )):
            ax.scatter(
                [pair[j][i] for pair in marks], [p + (j * 2 - 1) * 0.15 for p in positions],
                marker=mark, color=color, label=caption, s=31, zorder=3,
            )
        for separator in separators[:-1]:
            ax.axhline(separator, color="#d9dfe2", linewidth=0.9)
        ax.set_title(title, loc="left", fontsize=12)
        ax.grid(axis="x", color="#e8edef", linewidth=0.65)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[2].legend(loc="lower right", frameon=True)
    fig.suptitle("Shared clock effect on matched receiver fits", fontsize=16, x=0.01, ha="left")
    fig.supxlabel("Clock on minus exact clock-off. Negative values indicate lower error or RMS.")
    fig.savefig(REPORT / "rf-and-position-deltas.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--custom", action="store_true")
    args = parser.parse_args()
    custom() if args.custom else prepare()
