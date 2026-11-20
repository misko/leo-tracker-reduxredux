"""Score held trackless rate evidence separately from geographic errors."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import trackless_likelihood_trial as trial
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT, world, WAVE = trial.OUT, trial.world, trial.WAVE
CENTER = "trackless_tile_center"
FIELDS = (
    "slices",
    "held_slices",
    "held_blocks",
    "endpoint_pairs",
    "sites",
    "modeled_orbits",
    "exact_rate_evaluations",
    "rate_kernel_hz_s",
    "held_location_lead",
    "held_log_score",
    "train_log_score",
    "held_center_log_score",
    "held_signal_probability",
    "held_effective_competing_orbits",
    "held_conditional_rate_rms_hz_s",
)


def authorities():
    root = world.prior.archive.REPORT
    original = world.prior.archive.base.secant_full.REPORT
    world.verify(root, world.read(root / "omitted-figure-lock.json")["files"])
    world.verify(original, world.read(original / "receipt.json")["files"])
    world.verify(WAVE, world.read(WAVE / "figure-lock.json")["files"])
    return (
        {
            r["id"]: r
            for panel in ("ds26-common127", "roof16")
            for r in world.prior.archive.base.phase.corpus.references(panel)
        },
        world.read(original / "original-v5-inputs.json"),
        {r["id"]: r for r in world.read(root / "omitted-queries.json")["queries"]},
        {r["id"]: r for r in world.read(WAVE / "chart-queries.json")["queries"]},
        {(r["id"], r["arm"]): r for r in world.read(WAVE / "scores.json")["position"]},
    )


def compare_original(row, wave, omitted, refs, raw_original, installed):
    ident, case = row["id"], row["recording"]
    if ident in wave:
        q = wave[ident]
        match = {"input_sha256": "original_request_sha256", "catalogue_sha256": "catalog_sha256"}
        if any(row[match.get(k, k)] != v for k, v in q["bindings"].items()):
            raise ValueError("waveform offer differs from its archived native and request")
        return q["truth"], "waveform", q["condition"], {}, {a: installed[ident, a] for a in ARMS}
    p = refs[case]["truth"]
    if ident in omitted:
        q = omitted[ident]
        if p != q["truth"] or any(
            row["original_request_sha256" if k == "input_sha256" else k] != v
            for k, v in q["bindings"].items()
        ):
            raise ValueError("omitted offer does not match the frozen input")
        return p, "omitted", "omitted", {}, {}
    return (
        p,
        "containing",
        "containing",
        original_scores(case, refs[case], raw_original[case], p),
        {},
    )


def score():
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    refs, original, omitted, wave, installed = authorities()
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    records = {(r["id"], r["method"]): r for r in rows}
    if len(rows) != len(records) or set(records) != {
        (q["id"], m) for q in plan["cases"] for m in trial.model.METHODS
    }:
        raise ValueError("prediction rosters differ from the lock")
    scores, panels, centres = [], {}, []
    for q in plan["cases"]:
        key = q["id"]
        primary = records[key, trial.model.METHODS[0]]
        truth, panel, condition, roof, waveform = compare_original(
            primary, wave, omitted, refs, original, installed
        )
        if (roi_margin(truth, q["tile"]) >= 0) != (condition == "containing"):
            raise ValueError("sealed offer relation differs from published truth")
        binding = {k: primary[k] for k in MATCH}
        panels.setdefault(panel, []).append(
            dict(
                id=key,
                recording=primary["recording"],
                truth=truth,
                condition=condition,
                bindings=binding,
            )
        )
        center = q["tile"]["center"]
        centres.append(
            dict(
                primary,
                method=CENTER,
                result=dict(
                    status="ok",
                    reason=None,
                    boundary="Unconditional supplied tile centre",
                    metrics={},
                    arms={a: dict(latlon=center, forced_latlon=None) for a in ARMS},
                ),
            )
        )
        for method in trial.model.METHODS:
            r = records[key, method]
            if any(r.get(k) != v for k, v in (binding | q).items()):
                raise ValueError("control received a different native input or spatial offer")
            result = r["result"]
            if result["arms"]["c0"] != result["arms"]["fitted_c"]:
                raise ValueError("same-lane CFO differences must cancel fixed c")
            m = result["metrics"]
            arms = result["arms"]
            for arm in ARMS:
                end = arms[arm]
                extra = waveform.get(arm, {})
                values = m.get("modeled_rate_change_25km_hz_s") or [None, None, None]
                delta = m.get("held_control_leads", [None, None])
                scores.append(
                    dict(
                        id=key,
                        recording=q["recording"],
                        panel=panel,
                        condition=condition,
                        method=method,
                        arm=arm,
                        status=result["status"],
                        reason=result["reason"],
                        error_km=distance_km(end["latlon"], truth),
                        forced_error_km=distance_km(end["forced_latlon"], truth),
                        tile_center_error_km=distance_km(center, truth),
                        conditional_installed_cfo_rms_hz=extra.get("rf_rms_hz"),
                        installed_error_km=extra.get("position_error_km"),
                        position_attempted=m.get("position_attempted", False),
                        rate_change_25km_p10_hz_s=values[0],
                        rate_change_25km_median_hz_s=values[1],
                        rate_change_25km_p90_hz_s=values[2],
                        held_shifted_lead=delta[0],
                        held_density_lead=delta[1],
                        wall_s=r.get("native_elapsed_s"),
                        cpu_s=r.get("cpu_s"),
                        peak_rss_kib=r.get("peak_rss_kib"),
                        **{k: m.get(k) for k in FIELDS},
                        **{
                            role + "_error_km": roof[role][arm][0] if role in roof else None
                            for role in ROLES
                        },
                        **{
                            role + "_cfo_rms_hz": roof[role][arm][1] if role in roof else None
                            for role in ROLES
                        },
                    )
                )
    save_json(OUT / "scores.json", dict(rows=scores))
    csv_file(OUT / "scores.csv", scores)
    plot(scores)
    bind = lock["files"] | {
        name: world.digest((OUT / name).read_bytes())
        for name in (
            "scores.json",
            "scores.csv",
            "prediction-lock.json",
            "likelihood-support.png",
        )
    }
    save_json(OUT / "score-lock.json", dict(cases=lock["cases"], files=bind))
    figures(panels, rows + centres, bind)


def plot(scores):
    import matplotlib.pyplot as plt

    data = [
        r
        for r in scores
        if r["arm"] == "c0" and r["method"] == trial.model.METHODS[0] and r["position_attempted"]
    ]
    if not data:
        return
    i = range(len(data))
    fig, (a, b) = plt.subplots(1, 2, figsize=(12.5, 5.5), layout="constrained")
    a.scatter(
        [r["rate_change_25km_median_hz_s"] for r in data],
        i,
        marker="D",
        label="Median modeled 25 km rate change",
    )
    a.scatter(
        [r["rate_kernel_hz_s"] for r in data], i, marker="x", label="Measurement kernel width"
    )
    b.scatter([r["held_location_lead"] for r in data], i, marker="o", label="Separated grid rival")
    b.scatter([r["held_shifted_lead"] for r in data], i, marker="D", label="Time-shift control")
    b.scatter([r["held_density_lead"] for r in data], i, marker="x", label="Density-only control")
    b.axvline(0, linewidth=1, color="grey")
    for ax in (a, b):
        ax.set(
            yticks=list(i),
            yticklabels=[
                r["id"] if r["panel"] != "waveform" else "Waveform " + r["condition"] for r in data
            ],
        )
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    a.set(title="Known-orbit spatial sensitivity", xlabel="Hz/s at 11.5 GHz")
    b.set(
        title="Held score advantages at the selected site", xlabel="Mean log likelihood difference"
    )
    fig.savefig(OUT / "likelihood-support.png", dpi=150)
    plt.close(fig)


def figures(panels, records, frozen):
    cards = []
    for panel, queries in panels.items():
        transfer = panel != "containing"
        cases = [q["id"] for q in queries]
        positions, seal = f"{panel}-positions.jsonl.gz", f"{panel}-figure-lock.json"
        files = frozen | {positions: pack(OUT, positions, [r for r in records if r["id"] in cases])}
        title = {
            "containing": "Trackless likelihood on containing roof offers",
            "omitted": "Trackless likelihood on real omitted roof offers",
            "waveform": "Trackless likelihood on previously emitted Qin waveform",
        }[panel]
        card = dict(
            id=f"{trial.model.METHODS[0]}-{panel}",
            method=trial.model.METHODS[0],
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=title,
            caption="Raw GLRT rate mixtures, matched nulls and supplied centre.",
            seal=seal,
            provenance=["blind-plan.json", "prediction-lock.json", "scores.json"],
            series=[],
        )
        keys = (
            ("candidate", "stock", "one", "four")
            if transfer
            else ("one", "stock", "one_native_factors", "all_visits")
        )
        for key, method, label in zip(
            keys,
            (*trial.model.METHODS, CENTER),
            (
                "Synchronous likelihood",
                "Time-shift control",
                "Density-only control",
                "Tile centre prior",
            ),
            strict=True,
        ):
            line = dict(key=key, value=method, label=label, file=positions)
            if method != trial.model.METHODS[0]:
                line["match"] = list(MATCH)
            if method != CENTER and (transfer or method == trial.model.METHODS[0]):
                line["forced_label"] = label + " · forced"
            card["series"].append(line)
        if transfer:
            query = panel + "-queries.json"
            save_json(OUT / query, dict(queries=queries))
            files[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


if __name__ == "__main__":
    score()
