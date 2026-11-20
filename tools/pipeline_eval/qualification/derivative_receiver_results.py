"""Score sealed geometry, preparation domains and the two matched derivative modes."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import derivative_receiver_trial as trial
from .armijo_finish_results import pack
from .native_joint_full_results import original_scores, roi_margin
from .prefix_figures import csv_file

OUT = trial.OUT
MATCH = tuple(k for k in trial.MATCH if k != "tile")
METRICS = (
    "anonymous_arcs",
    "eligible_arcs",
    "disjoint_pairs",
    "grid_sites",
    "regional_orbits",
    "informative_orbits",
    "raw_25km_rms_hz",
    "affine_removed_25km_rms_hz",
    "phase_projected_25km_singular",
    "forced_identity_25km_singular",
    "held_spatial_advantage",
)


def get_rows(name):
    with gzip.open(OUT / name, "rt") as stream:
        return list(map(json.loads, stream))


def verification(plan):
    root = trial.prior.archive.REPORT
    original = trial.prior.archive.base.secant_full.REPORT
    verify = trial.prior.archive.base.secant_full._verify_files
    verify(root, trial.read(root / "omitted-figure-lock.json")["files"])
    verify(original, trial.read(original / "receipt.json")["files"])
    physical = trial.FIELD_PLAN.parent
    verify(physical, trial.read(physical / "figure-lock.json")["files"])
    sha = trial.digest((trial.clock.SITE_REPORT / "input-lock.json").read_bytes())
    if sha != plan["site_lock_sha256"]:
        raise ValueError("earlier synthetic input receipt differs from the frozen trial")
    expected = trial.read(trial.clock.SITE_REPORT / "input-lock.json")["files"][
        "private/labels.json"
    ]
    if trial.digest((trial.clock.SITE_REPORT / "labels.json").read_bytes()) != expected:
        raise ValueError("synthetic site labels differ from the original commitment")
    return (
        {q["id"]: q for q in trial.read(root / "omitted-queries.json")["queries"]},
        trial.read(original / "original-v5-inputs.json"),
        {q["id"]: q for q in trial.read(physical / "figure-queries.json")["queries"]},
        trial.read(trial.clock.SITE_REPORT / "labels.json"),
    )


def score():
    lock = trial.read(OUT / "prediction-lock.json")
    trial.prior.archive.base.secant_full._verify_files(OUT, lock["files"])
    plan = trial.read(OUT / "blind-plan.json")
    wrong, original, field, simulated = verification(plan)
    official = {
        r["id"]: r
        for panel in ("ds26-common127", "roof16")
        for r in trial.prior.archive.base.phase.corpus.references(panel)
    }
    actual = {(r["id"], r["method"]): r for r in get_rows("positions.jsonl.gz")}
    (null,) = get_rows("null-position.jsonl.gz")
    axes = dict(omitted=[], simulated=[], field=[])
    scores = []
    for q in plan["cases"]:
        key, scope = q["id"], q["cohort"]
        if key == trial.NULL:
            if null["id"] != key or null["orbit_ns_shift"] != q["orbit_ns_shift"]:
                raise ValueError("wrong or missing orbit-time control")
            continue
        a = actual[key, trial.variant.METHOD]
        if any(a.get(k) != value for k, value in q.items()):
            raise ValueError("run input differs from the frozen query")
        case = q["recording"]
        geo_ref = {}
        if scope.startswith("field"):
            source = field[key]
            if (
                source["recording"] != case
                or source["bindings"]["input_sha256"] != q["original_request_sha256"]
            ):
                raise ValueError("prepared field query differs from the original published offer")
            truth, cohort, condition = source["truth"], "field", scope.removeprefix("field-")
        elif scope.startswith("simulated"):
            source = simulated[key]
            if source["capture_id"] != case or "simulated-" + source["condition"] != scope:
                raise ValueError("synthetic capture and offer provenance changed")
            truth, cohort, condition = source["latlon"], "simulated", source["condition"]
        else:
            ref = official[case]
            truth, cohort, condition = ref["truth"], scope, scope
            if scope == "omitted":
                source = wrong[key]
                if source["truth"] != truth or any(
                    a["original_request_sha256" if k == "input_sha256" else k] != v
                    for k, v in source["bindings"].items()
                ):
                    raise ValueError("omitted query differs from archived native and tile request")
            else:
                geo_ref = original_scores(key, ref, original[key], truth)
        inside = roi_margin(truth, q["tile"]) >= 0
        if inside != (scope in ("diagnostic", "reserve", "simulated-present", "field-present")):
            raise ValueError("supplied tile relation does not match the sealed scoring condition")
        if cohort in axes:
            axes[cohort].append(
                dict(
                    id=key,
                    recording=case,
                    truth=truth,
                    condition=condition,
                    bindings={k: a[k] for k in MATCH},
                )
            )
        for method in trial.METHODS:
            r = actual[key, method]
            if any(r[k] != a[k] for k in trial.MATCH):
                raise ValueError(
                    "two derivative modes use different native inputs or offered regions"
                )
            status = r["result"]["status"]
            arms = r["result"]["arms"]
            c0, fitted = arms["c0"], arms["fitted_c"]
            for name in ("latlon", "forced_latlon", "rf_rms_hz", "held_rms_hz"):
                if c0.get(name) != fitted.get(name):
                    raise ValueError("projected coefficient changed the identical fit")
            metric = r["result"]["metrics"]
            for arm in ARMS:
                point = arms[arm]
                scores.append(
                    dict(
                        id=key,
                        recording=case,
                        cohort=scope,
                        method=method,
                        arm=arm,
                        status=status,
                        reason=r["result"]["reason"],
                        error_km=distance_km(point["latlon"], truth),
                        forced_error_km=distance_km(point["forced_latlon"], truth),
                        tile_error_km=distance_km(q["tile"]["center"], truth),
                        training_rf_rms_hz=point.get("rf_rms_hz"),
                        held_rf_rms_hz=point.get("held_rms_hz"),
                        held_points=point.get("held_points"),
                        wall_s=r["native_elapsed_s"],
                        cpu_s=r.get("cpu_s"),
                        peak_rss_kib=r.get("peak_rss_kib"),
                        **{k: metric.get(k) for k in METRICS},
                        **{
                            role + "_error_km": geo_ref[role][arm][0] if role in geo_ref else None
                            for role in ROLES
                        },
                        **{
                            role + "_rf_rms_hz": geo_ref[role][arm][1] if role in geo_ref else None
                            for role in ROLES
                        },
                    )
                )
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(rows=scores, orbit_time_negative=null))
    sources = ("prediction-lock.json", "blind-plan.json", "scores.json")
    files = lock["files"] | {name: trial.digest((OUT / name).read_bytes()) for name in sources}
    cards = []
    for name, title, caption in (
        (
            "diagnostic",
            "Polynomial Doppler derivatives on diagnostic roof recordings",
            "Anonymous native GLRT, one causal TLE and the original containing offer.",
        ),
        (
            "reserve",
            "Polynomial Doppler derivatives on held roof recordings",
            "Four prespecified archived roof recordings with the same native input and phase grid.",
        ),
        (
            "omitted",
            "Polynomial Doppler derivatives with the true roof omitted",
            "Authenticated real native GLRT with its genuinely omitted offer.",
        ),
        (
            "simulated",
            "Polynomial Doppler derivatives at two new simulated sites",
            "Simulated native GLRT with measured archive frequency disturbances.",
        ),
        (
            "field",
            "Polynomial derivatives of measured StarLoc beacons",
            "Prepared single-band beacon measurements using the independent curvature path.",
        ),
    ):
        transfer = name in axes
        cases = (
            [o["id"] for o in axes[name]]
            if transfer
            else [q["id"] for q in plan["cases"] if q["cohort"] == name]
        )
        positions = name + "-positions.jsonl.gz"
        files[positions] = pack(
            OUT, positions, [r for (key, _), r in actual.items() if key in cases]
        )
        receipt = name + "-figure-lock.json"
        card = dict(
            id=f"{trial.variant.METHOD}-{name}",
            method=trial.variant.METHOD,
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=title,
            caption=caption,
            seal=receipt,
            provenance=list(sources),
            series=[],
        )
        for k, method, label in zip(
            ("candidate" if transfer else "one", "stock"),
            trial.METHODS,
            ("Differential slope and curvature", "Independent curvature"),
            strict=True,
        ):
            row = dict(key=k, label=label + " · publication", file=positions, value=method)
            if transfer or method == trial.variant.METHOD:
                row["forced_label"] = label + " · forced"
            if k == "stock":
                row["match"] = list(MATCH)
            card["series"].append(row)
        if transfer:
            query = name + "-queries.json"
            save_json(OUT / query, dict(queries=axes[name]))
            files[query] = trial.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / receipt, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))
    return scores


def diagnostic_plot(rows):
    import matplotlib.pyplot as plt
    import numpy as np

    data = [
        r
        for r in rows
        if r["arm"] == "c0"
        and r["method"] == trial.variant.METHOD
        and r["cohort"] in ("diagnostic", "reserve")
    ]
    i = np.arange(len(data))
    fig, axis = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for x, key, title in (
        (axis[0], "Doppler shift (Hz RMS)", "Exact 25 km shift before and after affine removal"),
        (axis[1], "Smallest spatial singular value", "Phase-projected position sensitivity"),
    ):
        x.set_ylabel(key)
        x.set_title(title)
        x.set_xticks(i, [r["id"] for r in data], rotation=30, ha="right")
        x.grid(axis="y", alpha=0.3)
    for j, (key, label, color) in enumerate(
        (
            ("raw_25km_rms_hz", "Full CFO", "#52668A"),
            ("affine_removed_25km_rms_hz", "After affine projection", "#168775"),
        )
    ):
        axis[0].bar(
            i + (j - 0.5) * 0.31, [r[key] for r in data], width=0.31, color=color, label=label
        )
    axis[0].set_yscale("log")
    for j, (key, label, color) in enumerate(
        (
            ("forced_identity_25km_singular", "All forced identities", "#52668A"),
            ("phase_projected_25km_singular", "Held-supported identities", "#168775"),
        )
    ):
        axis[1].bar(
            i + (j - 0.5) * 0.31,
            [r[key][-1] if r[key] is not None else 0 for r in data],
            width=0.31,
            color=color,
            label=label,
        )
    axis[1].axhline(3, linestyle="--", linewidth=1.2, color="black", label="Publication floor")
    for x in axis:
        x.legend(fontsize=8)
    fig.savefig(OUT / "derivative-observability.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    diagnostic_plot(score())
