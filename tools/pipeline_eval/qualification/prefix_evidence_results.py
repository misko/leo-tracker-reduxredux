"""Score the frozen prefix choice separately from genuine switched compact fits."""

import argparse
import csv
from pathlib import Path
from statistics import median

from .. import whole_iq
from ..__main__ import ROOT, save_json
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import fresh_replay
from . import prefix_evidence_trial as trial
from .bracketed_position_results import scientific
from .complete_detector_roster import BINDINGS, FIVE, FOUR
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

METHODS = ("stock", "fifth", "prefix", "oracle")


def sealed(folder, name, seal):
    return whole_iq.checked(folder / name, seal["files"][name])


def retrospective(choices, official):
    with sealed(trial.OFFICIAL, "scores.csv", official).open() as f:
        fixed = {
            (r["id"], r["method"], r["arm"]): r
            for r in csv.DictReader(f)
            if r["method"] in (FOUR, FIVE)
        }
    if set(fixed) != {(i, m, a) for i in choices for m in (FOUR, FIVE) for a in ARMS}:
        raise ValueError("Fixed entire-branch score coverage changed")
    data = []
    for ident, choice in choices.items():
        for arm in ARMS:
            a, b = (fixed[ident, m, arm] for m in (FOUR, FIVE))
            stock = float(a["error_km"]) if a["error_km"] else None
            fifth = float(b["error_km"]) if b["error_km"] else None
            before = float(a["baseline_km"])
            if before != float(b["baseline_km"]):
                raise ValueError("Fixed receivers have different capture-era v5 references")
            prefix = stock if choice["chosen"] == "stock" else fifth
            oracle = min((v for v in (stock, fifth) if v is not None), default=None)
            data.append(
                dict(
                    id=ident,
                    arm=arm,
                    scope="retrospective_entire_branch",
                    chosen=choice["chosen"],
                    stock=stock,
                    fifth=fifth,
                    prefix=prefix,
                    oracle=oracle,
                    fixed_v5_km=before,
                    net=choice["net"],
                    net_first_half=choice["net_by_half"][0],
                    net_second_half=choice["net_by_half"][1],
                    gained_lanes=choice["gained_lanes"],
                    unchanged_from_stock=prefix == stock,
                )
            )
    return data


def summary(rows):
    out = {}
    for arm in ARMS:
        data = [r for r in rows if r["arm"] == arm]
        out[arm] = {}
        for mode in METHODS:
            delta = [r[mode] - r["stock"] for r in data if None not in (r[mode], r["stock"])]
            out[arm][mode] = dict(
                **distribution(r[mode] for r in data),
                scheduled=len(data),
                improved_vs_stock=sum(d < 0 for d in delta),
                worsened_vs_stock=sum(d > 0 for d in delta),
                within_10pct_of_v5=sum(
                    r[mode] is not None and r[mode] <= 1.10 * r["fixed_v5_km"] for r in data
                ),
            )
    return out


def true_fits(identities, paths):
    fits, sources = [], {}
    for ident in identities:
        name = f"{ident}-fit.json"
        folder = paths / ident
        nested = trial.REPORT / name
        row = whole_iq.read(nested)
        for asset, digest in row["files"].items():
            whole_iq.checked(folder / asset, digest)
        whole_iq.checked(folder / "recording/native.json", row["native_sha256"])
        whole_iq.checked(folder / "recording/request.json", row["bound_request_sha256"])
        validate_result(row["result"])
        if row["id"] != ident:
            raise ValueError("Mixed fit has the wrong case identity")
        for key in ("native_sha256", "original_request_sha256", "paired_capture_sha256"):
            if row[key] != whole_iq.read(folder / "fit-binding.json")[key]:
                raise ValueError("Fresh position receipt changed its execution identity")
        fits.append(row)
        sources[name] = _sha(nested)
        if ident in trial.FRESH:
            name = f"{ident}-choice.json"
            sources[name] = _sha(trial.REPORT / name)
    return fits, sources


def controls_for(fits, official):
    fresh = trial.receiver_choice_panel.REPORT
    fresh_predictions = whole_iq.read(fresh / "prediction-lock.json")
    published_raw = whole_iq.read(fresh / "raw-prediction-lock.json")
    authority = whole_iq.read(sealed(fresh, "raw-authority.json", published_raw))
    raw = rows_from(sealed(trial.OFFICIAL, "all-positions.jsonl.gz", official))
    raw += rows_from(sealed(fresh, "positions.jsonl.gz", fresh_predictions))
    allowed = {
        FOUR: "stock",
        FIVE: "fifth",
        trial.receiver_choice_panel.STOCK: "stock",
        trial.receiver_choice_panel.METHOD: "fifth",
    }
    rows = {(r["id"], allowed[r["method"]]): r for r in raw if r["method"] in allowed}
    for fit in fits:
        ident = fit["id"]
        for mode, role in (("stock", "control"), ("fifth", "candidate")):
            direct = rows[ident, mode]
            expected = fit["source"][mode]["sha256"]
            if direct["native_sha256"] != expected or any(fit[k] != direct[k] for k in BINDINGS):
                raise ValueError("Mixed and full branch results use different waveform or request")
            if ident in trial.FRESH and authority[ident][role]["native_sha256"] != expected:
                raise ValueError("Provisional fresh handoff differs from sealed waveform")
            if (
                fit["choice"]["chosen"] == "stock"
                and mode == "stock"
                and (
                    fit["native_sha256"] != expected
                    or scientific(fit["result"]) != scientific(direct["result"])
                )
            ):
                raise ValueError("Stock fallback did not independently reproduce stock science")
    return rows, {
        str((fresh / name).relative_to(trial.SCREEN)): _sha(fresh / name)
        for name in ("prediction-lock.json", "raw-prediction-lock.json")
    }


def actual_scores(fits, control):
    older = [r["id"] for r in fits if r["id"] != "DS29-0491"]
    _, held = held_references(None, older)
    roof = {r["id"]: r["truth"] for r in held}
    path = whole_iq.checked(
        fresh_replay.DS29 / "evaluation-references.json", fresh_replay.TRUTH_SHA
    )
    record = whole_iq.read(path)["DS29-0491"]
    roof["DS29-0491"] = [record["latitude_deg"], record["longitude_deg"]]
    rows, scores = [], []
    for fit in fits:
        i = fit["id"]
        candidates = (control[i, "stock"], control[i, "fifth"], fit)
        rows.extend(candidates)
        for arm in ARMS:
            errors = {}
            for mode, r in zip(("stock", "fifth", "prefix"), candidates, strict=True):
                estimate = r["result"].get("arms", {}).get(arm, {})
                errors[mode] = distance_km(estimate.get("latlon"), roof[i])
                errors[f"{mode}_status"] = r["result"]["status"]
                errors[f"{mode}_rf_rms_hz"] = estimate.get("rf_rms_hz")
                errors[f"{mode}_frequency_score"] = r["result"]["metrics"].get(
                    f"{arm}_frequency_score"
                )
            scores.append(
                dict(
                    id=i,
                    arm=arm,
                    scope="actual_compact_stock_warmup",
                    chosen=fit["choice"]["chosen"],
                    **errors,
                    **fit["counts"],
                    fit_cpu_s=fit["resources"]["cpu_s"],
                    fit_wall_s=fit["resources"]["wall_s"],
                    native_sha256=fit["native_sha256"],
                )
            )
    return rows, scores


def figure(choices, totals, measured):
    import matplotlib

    matplotlib.use("Agg")
    import numpy as np
    from matplotlib import pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(12.9, 5.6), layout="constrained")
    cases = list(choices)
    axes[0].barh(
        cases,
        [choices[c]["net"] for c in cases],
        color=["#00776F" if choices[c]["chosen"] == "fifth" else "#657687" for c in cases],
    )
    axes[0].invert_yaxis()
    axes[0].axvline(8, linestyle="--", color="#A66E37", linewidth=0.9)
    axes[0].set(
        title="Frozen 24 s signal decision",
        xlabel="Net recurring pilot endpoints · teal selects fifth",
    )
    axes[0].tick_params(axis="y", labelsize=7)
    colors = ("#657687", "#386A95", "#00776F", "#9B703E")
    names = ("Stock four", "Fixed fifth", "Prefix choice", "Oracle bound")
    for z, arm in enumerate(ARMS):
        values = [totals[arm][n]["p50"] for n in METHODS]
        bars = axes[1].barh(
            np.arange(4) + (z - 0.5) * 0.32,
            values,
            0.29,
            color=colors,
            alpha=0.70 if z else 1,
            hatch="//" if z else None,
        )
        axes[1].bar_label(bars, fmt="%.2f", fontsize=8, padding=2)
    axes[1].set(
        title="Entire-branch substitution · 20",
        xlabel="Median position error (km)",
        yticks=range(4),
        yticklabels=names,
        xlim=(0, max(totals[a][m]["p50"] for a in ARMS for m in METHODS) * 1.23),
    )
    axes[1].invert_yaxis()
    ax = axes[2]
    y = range(len(measured))
    for r, mode in enumerate(("stock", "fifth", "prefix")):
        ax.scatter(
            [d[mode] for d in measured],
            [v + (r - 1) * 0.16 for v in y],
            c=colors[r],
            s=26,
            label=names[r],
            marker=("o", "s", "D")[r],
        )
    ax.set(
        title=f"Actual adaptive compact · {len(measured) // 2}",
        xlabel="Position error (km)",
        yticks=list(y),
        yticklabels=[f"{d['id']} · {'c=0' if d['arm'] == 'c0' else 'fitted'}" for d in measured],
    )
    ax.invert_yaxis()
    ax.legend(fontsize=7, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.10), ncols=3)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="x", color="#E2E8EC", linewidth=0.6)
        ax.set_axisbelow(True)
    fig.suptitle(
        "Choose four or five timing regions from early pilot recurrence\n"
        "Center panel uses sealed fixed branches · hatched bars are fitted calibration"
    )
    fig.savefig(trial.REPORT / "stage.png", dpi=155)
    fig.savefig(trial.REPORT / "stage.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def publish(work):
    _, choices = trial.verified(work)
    ids = [choices["actual_old_case"], *trial.FRESH]
    fits, files = true_fits(ids, work)
    save_json(
        trial.REPORT / "fit-lock.json",
        dict(cases=ids, files=files, choices_sha256=_sha(trial.REPORT / "choices.json")),
    )
    official = whole_iq.read(trial.OFFICIAL / "all-figure-lock.json")
    control, input_digests = controls_for(fits, official)
    rows, actual = actual_scores(fits, control)
    data = retrospective(choices["cases"], official)
    totals = summary(data)
    out = trial.REPORT
    csv_file(out / "stage.csv", data)
    csv_file(out / "actual-scores.csv", actual)
    pack(out / "actual-positions.jsonl.gz", rows)
    save_json(
        out / "summary.json",
        dict(
            retrospective=totals,
            actual=actual,
            fifth_choices=sum(d["chosen"] == "fifth" for d in choices["cases"].values()),
            prefix_feature_cpu_p50_ms=median(
                n / 1e6 for d in choices["cases"].values() for n in d["cpu_ns"]
            ),
            full_iq_service_reexecuted=False,
        ),
    )
    figure(choices["cases"], totals, actual)
    save_json(
        out / "stage-figure.json",
        dict(
            version=1,
            id="prefix-evidence",
            title="Causal pilot recurrence as a detector choice",
            boundary="24 s pilot prefix → fixed branch choice → mixed factors and compact fit",
            sample="20 retrospective fixed-branch choices and three actual compact factor runs",
            note="The selector uses native radio only. The compact fits use mixed factor inputs.",
            seal="prediction-lock.json",
            image="stage.png",
            pdf="stage.pdf",
            csv="stage.csv",
        ),
    )
    files.update(
        {
            n: _sha(out / n)
            for n in (
                "README.md",
                "PROTOCOL.md",
                "source-lock.json",
                "choices.json",
                "fit-lock.json",
                "actual-positions.jsonl.gz",
                "stage.csv",
                "actual-scores.csv",
                "summary.json",
                "stage.png",
                "stage.pdf",
                "stage-figure.json",
            )
        }
    )
    sources = (
        Path(__file__),
        Path(__file__).with_name("prefix_evidence_position.py"),
        ROOT / "tests/pipeline_eval/test_prefix_evidence.py",
    )
    input_digests[str((trial.OFFICIAL / "all-figure-lock.json").relative_to(trial.SCREEN))] = _sha(
        trial.OFFICIAL / "all-figure-lock.json"
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(choices["cases"]),
            actual_cases=ids,
            files=files,
            input_receipts=input_digests,
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=trial.WORK)
    publish(p.parse_args().work)
