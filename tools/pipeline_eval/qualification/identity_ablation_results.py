"""Score sealed fixed-orbit estimates and the exact shared held rows."""

import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..__main__ import save_json
from ..scoring import ROLES, distance_km
from . import identity_ablation as trial
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
MATCH = ("native_sha256", "catalog_sha256", "input_sha256")


def read_rows(path):
    with gzip.open(path, "rt") as stream:
        return list(map(json.loads, stream))


def common_held(cells, available):
    keys = trial.CELLS[2:]
    paired = [cells[k] for k in keys]
    active = []
    for k in keys:
        train = [
            r for r in cells[k] if trial.fit.training(r["time_s"]) and r["norad"] in available[k]
        ]
        active.append(({r["norad"] for r in train}, {trial._narrow(r)[-1] for r in train}))
    found = []
    for a, b in zip(*paired, strict=True):
        if (
            a["observation_id"],
            a["candidate_rank"],
            a["time_s"],
            a["measured_cfo_hz"],
            a["rf_hz"],
        ) != (
            b["observation_id"],
            b["candidate_rank"],
            b["time_s"],
            b["measured_cfo_hz"],
            b["rf_hz"],
        ):
            raise ValueError("shared plot no longer compares the exact physical observations")
        if trial.fit.held(a["time_s"]) and all(
            r["norad"] in o and trial._narrow(r)[-1] in group
            for r, (o, group) in zip((a, b), active, strict=True)
        ):
            found.append((a, b))
    return found


def tle_inventory(case, selected):
    ref = trial._load_case(case)
    raw = (trial.BULK / ref["catalog"]["path"]).read_bytes()
    if trial.digest(raw) != ref["catalog"]["sha256"]:
        raise ValueError("TLE audit failed checksum")
    lines = [s.rstrip() for s in raw.splitlines() if s.startswith((b"1 ", b"2 "))]
    catalogue = trial.fit.parse_element_sets(raw.decode())
    latest = {}
    collected, cutoff = ref["catalog_timestamp_ns"], ref["cutoff_utc_ns"]
    for number, epoch, i in zip(
        catalogue.satellite_numbers,
        catalogue.element_epoch_utc_ns(),
        range(0, len(lines), 2),
        strict=True,
    ):
        if (
            number in selected
            and cutoff - trial.fit.grid.MAX_TLE_AGE_NS <= epoch <= collected
            and (number not in latest or epoch > latest[number]["epoch_utc_ns"])
        ):
            latest[number] = dict(
                id=case,
                norad=number,
                epoch_utc_ns=epoch,
                collected_utc_ns=collected,
                hours_from_epoch_to_cutoff=(cutoff - epoch) / 3.6e12,
                causal_catalogue_sha256=ref["catalog"]["sha256"],
                two_line_sha256=trial.digest(lines[i] + b"\n" + lines[i + 1] + b"\n"),
            )
    if set(latest) != selected:
        raise ValueError("some fitted orbits lack an authenticated causal element")
    return list(latest.values())


def score():
    lock = trial.read(OUT / "prediction-lock.json")
    verify = trial.prior.archive.base.secant_full._verify_files
    verify(OUT, lock["files"])
    plan = trial.read(OUT / "blind-plan.json")
    original = trial.prior.archive.base.secant_full.REPORT
    verify(original, trial.read(original / "receipt.json")["files"])
    if plan["v5_receipt_sha256"] != trial.digest((original / "receipt.json").read_bytes()):
        raise ValueError("original positions differ from the prospectively bound archive")
    refs = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in trial.prior.archive.base.phase.corpus.references(panel)
    }
    roof = trial.read(original / "original-v5-inputs.json")
    f = {r["id"]: r["cells"] for r in read_rows(OUT / "factor-ledger.jsonl.gz")}
    prediction = {(r["id"], r["cell"]): r for r in read_rows(OUT / "positions.jsonl.gz")}
    scores, queries, inventory = [], [], []
    if set(lock["cases"]) != set(f) or len(prediction) != len(f) * len(trial.CELLS):
        raise ValueError("a planned cell is absent from the scoring denominator")
    for q in plan["cases"]:
        case = q["id"]
        ref = refs[case]
        truth = ref["truth"]
        baseline = original_scores(case, ref, roof[case], truth)
        result = {name: prediction[case, name] for name in trial.CELLS}
        a = result[trial.CELLS[0]]
        if roi_margin(truth, a["tile"]) < 0 or a["input_sha256"] != trial.digest(
            trial.encoded(q["packet"])
        ):
            raise ValueError("archive score does not use the intended original tile and input")
        queries.append(
            dict(
                id=case,
                condition=q["cohort"],
                recording=case,
                truth=truth,
                bindings={k: a[k] for k in MATCH},
            )
        )
        available = {k: set(row["result"]["metrics"]["orbit_order"]) for k, row in result.items()}
        paired = common_held(f[case], available)
        inventory.extend(tle_inventory(case, set.union(*available.values())))
        for name, r in result.items():
            if any(r[k] != a[k] for k in (*MATCH, "tile")):
                raise ValueError("fixed-identity comparison differs in original recording inputs")
            for arm, detail in r["result"]["arms"].items():
                c = trial.CELLS[2:].index(name) if name in trial.CELLS[2:] else None
                same = (
                    [pair[c].get("residuals", {}).get(arm) for pair in paired]
                    if c is not None
                    else []
                )
                common = np.array([value for value in same if value is not None])
                if 0 < len(common) != len(same):
                    raise ValueError("shared held residuals are missing inside the matched domain")
                scores.append(
                    dict(
                        id=case,
                        cohort=q["cohort"],
                        cell=name,
                        arm=arm,
                        forced_error_km=distance_km(detail["forced_latlon"], truth),
                        estimator_wall_s=r["wall_s"],
                        estimator_cpu_s=r["cpu_s"],
                        rss_kib=r["rss_kib"],
                        points=r["result"]["metrics"]["points"],
                        train_points=r["result"]["metrics"]["training_points"],
                        orbit_count=len(available[name]),
                        missing_causal_points=r["result"]["metrics"]["missing_causal_points"],
                        paired_held_points=len(common) if c is not None else None,
                        paired_held_rms_hz=trial.fit.rmshz(common),
                        **{
                            k: detail.get(k)
                            for k in (
                                "rf_rms_hz",
                                "held_rms_hz",
                                "held_points",
                                "c_hz_per_ghz",
                                "local_radius_km",
                                "weighted_horizontal_singular_values",
                                "below_geometric_horizon_points",
                            )
                        },
                        **{role + "_error_km": baseline[role][arm][0] for role in ROLES},
                        **{role + "_rms_hz": baseline[role][arm][1] for role in ROLES},
                    )
                )
    save_json(OUT / "scores.json", dict(rows=scores))
    csv_file(OUT / "scores.csv", scores)
    csv_file(OUT / "tle-inventory.csv", inventory)
    save_json(OUT / "scoring-queries.json", dict(queries=queries))
    provenance = (
        "blind-plan.json",
        "prediction-lock.json",
        "scores.json",
        "source-audit.json",
        "tle-inventory.csv",
    )
    files = lock["files"] | {
        name: trial.digest((OUT / name).read_bytes())
        for name in (*provenance, "scoring-queries.json")
    }
    cards = []
    for suffix, title, names in (
        ("full", "Fixed-orbit refit with each receiver’s measured peaks", trial.CELLS[:2]),
        ("shared", "Fixed-orbit refit on identical measured peaks", trial.CELLS[2:]),
    ):
        seal = f"{suffix}-figure-lock.json"
        save_json(OUT / seal, dict(cases=lock["cases"], files=files))
        cards.append(
            dict(
                id=f"identity_ablation-{suffix}",
                method=trial.METHOD,
                scope="transfer",
                cases=lock["cases"],
                title=title,
                queries="scoring-queries.json",
                seal=seal,
                caption="Forced rooftop estimates. Published v5 identities are a privileged input. "
                "Every refit uses the same physical estimator, causal TLE snapshot and offer.",
                condition_labels=dict(diagnostic="Diagnostics", reserve="Locked reserves"),
                provenance=list(provenance),
                series=[
                    dict(
                        key=key,
                        label=label + " · publication",
                        forced_label=label + " · forced",
                        file="positions.jsonl.gz",
                        value=trial.METHOD,
                        where=dict(cell=name),
                        **({"match": list(MATCH)} if key == "stock" else {}),
                    )
                    for key, name, label in zip(
                        ("candidate", "stock"),
                        names,
                        ("Anonymous identities", "Published v5 identities"),
                        strict=True,
                    )
                ],
            )
        )
    save_json(OUT / "figures.json", dict(version=1, charts=cards))
    return scores, f


def evidence(scores, factors, output):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
    colors = ("#047a64", "#435686", "#60af9e", "#8f9fca")
    cases = list(dict.fromkeys(r["id"] for r in scores))
    for i, arm in enumerate(trial.fit.ARMS):
        for k, (name, color) in enumerate(zip(trial.CELLS, colors, strict=True)):
            rows = [r for r in scores if r["cell"] == name and r["arm"] == arm]
            xx = np.arange(len(cases)) + 0.14 * (k - 1.5)
            label = name.replace("_", " ")
            ax[0, i].scatter(
                xx, [r["forced_error_km"] for r in rows], color=color, s=44, label=label
            )
            key = "paired_held_rms_hz" if name.startswith("shared") else "held_rms_hz"
            ax[1, i].scatter(xx, [r[key] for r in rows], color=color, s=44)
        base = [
            r["baseline_error_km"]
            for r in scores
            if r["cell"] == trial.CELLS[0] and r["arm"] == arm
        ]
        ax[0, i].scatter(
            range(len(cases)),
            base,
            facecolor="none",
            edgecolor="black",
            marker="D",
            label="published v5",
        )
        ax[0, i].set_title("c = 0" if arm == "c0" else "Fitted c")
        ax[0, i].set_ylabel("Horizontal position error (km)")
        ax[1, i].set_ylabel("Held Doppler RMS (Hz)")
        for panel in ax[:, i]:
            panel.set_xticks(range(len(cases)), cases, rotation=30, ha="right")
            panel.grid(axis="y", alpha=0.25)
            panel.set_yscale("log")
    ax[0, 1].legend(fontsize=8)
    fig.suptitle("Same estimator with anonymous and archived orbit identities", fontsize=17)
    fig.savefig(output / "position-and-held-rf.png", dpi=150)
    plt.close(fig)

    case = trial.DIAGNOSTIC[0]
    groups = defaultdict(list)
    for a, b in zip(*(factors[case][k] for k in trial.CELLS[2:]), strict=True):
        if a["norad"] != b["norad"] and all(
            r.get("residuals", {}).get("c0") is not None for r in (a, b)
        ):
            groups[a["receiver"], a["channel"], a["norad"], b["norad"]].append((a, b))
    if not groups:
        return
    (rx, channel, n1, n2), rows = max(groups.items(), key=lambda item: len(item[1]))
    x = np.array([a["time_s"] for a, _ in rows])
    y = np.array([a["measured_cfo_hz"] for a, _ in rows])
    margin = [a["margin"] for a, _ in rows]
    fig, (top, bot) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, layout="constrained")
    data = top.scatter(x, trial.fit.fold(y) / 1000, c=margin, s=25, cmap="plasma", zorder=3)
    fig.colorbar(data, ax=top, label="Native GLRT fractional margin")
    for axis in (top, bot):
        for a in np.arange(30, max(x) + 45, 60):
            if a < max(x) and a + 15 > min(x):
                axis.axvspan(a, a + 15, color="#dce7ee", alpha=0.7)
    for j, (identity, color) in enumerate(
        ((f"Anonymous · {n1}", colors[0]), (f"v5 · {n2}", colors[1]))
    ):
        residual = np.array([a[j]["residuals"]["c0"] for a in rows])
        top.scatter(
            x, trial.fit.fold(y - residual) / 1000, s=27, marker="x", color=color, label=identity
        )
        bot.scatter(x, residual, color=color, s=15)
    top.legend(loc="best")
    bot.axhline(0, color="#777777", linewidth=0.8)
    top.set_ylabel("Wrapped measured and predicted CFO (kHz)")
    bot.set_ylabel("Wrapped fit residual (Hz)")
    bot.set_xlabel("Capture time (s) · shading marks a held interval")
    fig.suptitle(
        f"{case} · RX{rx + 1} CH{channel} · {len(x)} identical peaks, different orbit labels"
    )
    fig.savefig(output / "shared-disagreement-cfo.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    evidence(*score(), Path(OUT))
