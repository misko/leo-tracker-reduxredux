"""Score exact archive bindings, held pass constraints and geographic endpoints."""

import gzip
import json

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import pass_hypotheses_trial as trial
from . import trackless_likelihood_results as shared
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
CENTER = "pass_hypotheses_tile_center"
FIELDS = (
    "linked_arcs",
    "used_arcs",
    "orbit_lines",
    "training_lines",
    "held_lines",
    "candidate_pairs",
    "in_tile_intersections",
    "median_line_hz_per_km",
    "checked_hypotheses",
    "pair_worst_axis_km",
    "train_rms_hz",
    "held_rms_hz",
    "held_supported_blocks",
    "held_cost",
    "held_spatial_lead",
    "held_mirror_lead",
    "position_attempted",
)


def score():
    lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, lock["files"])
    plan = world.read(OUT / "blind-plan.json")
    audit_lock = world.read(OUT / "conditioning-lock.json")
    world.verify(OUT, audit_lock["files"])
    audited = world.read(OUT / "conditioning.json")
    if audited["original_prediction_lock_sha256"] != world.digest(
        (OUT / "prediction-lock.json").read_bytes()
    ):
        raise ValueError("conditioning audit refers to a different prediction run")
    diagnostics = {r["id"]: r for r in audited["rows"]}
    refs, original, omitted, wave, installed = shared.authorities()
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        raw = list(map(json.loads, stream))
    predictions = {(r["id"], r["method"]): r for r in raw}
    if len(raw) != len(predictions) or set(predictions) != {
        (q["id"], mode) for q in plan["cases"] for mode in trial.model.METHODS
    }:
        raise ValueError("pass predictions do not cover the predeclared roster")
    scores, panels, tile = [], {}, []
    for q in plan["cases"]:
        ident = q["id"]
        primary = predictions[ident, trial.model.METHODS[0]]
        check = diagnostics[ident]
        audit = check["result"]
        if (
            check["input_sha256"] != primary["input_sha256"]
            or any(
                audit[k] != primary["result"]["metrics"].get(k)
                for k in ("used_arcs", "training_lines", "held_lines")
            )
            or audit["conditioned_inside_pairs"]
            != primary["result"]["metrics"].get("in_tile_intersections")
        ):
            raise ValueError("conditioning replay changed the original candidate inventory")
        truth, panel, condition, roof, waveform = shared.compare_original(
            primary, wave, omitted, refs, original, installed
        )
        if (roi_margin(truth, q["tile"]) >= 0) != (condition == "containing"):
            raise ValueError("offer has the wrong containment status")
        bind = {key: primary[key] for key in MATCH}
        panels.setdefault(panel, []).append(
            dict(
                id=ident,
                condition=condition,
                recording=q["recording"],
                truth=truth,
                bindings=bind,
            )
        )
        center = q["tile"]["center"]
        tile.append(
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
        for mode in trial.model.METHODS:
            row = predictions[ident, mode]
            if any(row[k] != v for k, v in (q | bind).items()):
                raise ValueError("mirrored control differs from frozen input")
            result = row["result"]
            if result["arms"]["c0"] != result["arms"]["fitted_c"]:
                raise ValueError("free per-pass intercept must absorb fixed RF calibration")
            for arm in ARMS:
                v = result["arms"][arm]
                comp = waveform.get(arm, {})
                scores.append(
                    dict(
                        id=ident,
                        recording=q["recording"],
                        panel=panel,
                        condition=condition,
                        method=mode,
                        status=result["status"],
                        arm=arm,
                        reason=result["reason"],
                        error_km=distance_km(v["latlon"], truth),
                        forced_error_km=distance_km(v["forced_latlon"], truth),
                        tile_error_km=distance_km(center, truth),
                        installed_error_km=comp.get("position_error_km"),
                        installed_conditional_rf_hz=comp.get("rf_rms_hz"),
                        cpu_s=row.get("cpu_s"),
                        wall_s=row["native_elapsed_s"],
                        peak_rss_kib=row.get("peak_rss_kib"),
                        **{k: result["metrics"].get(k) for k in FIELDS},
                        **{
                            k: val
                            for k, val in audit.items()
                            if k not in ("fixed_sites", "used_arcs", "training_lines", "held_lines")
                        },
                        **{
                            f"fixed_{site['east_km']}_held_rms_hz": site["held_rms_hz"]
                            for site in audit["fixed_sites"]
                        },
                        **{
                            f"fixed_{site['east_km']}_held_families": site["distinct_held_families"]
                            for site in audit["fixed_sites"]
                        },
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
    csv_file(OUT / "scores.csv", scores)
    save_json(OUT / "scores.json", dict(rows=scores))
    plot(scores)
    hashes = (
        lock["files"]
        | audit_lock["files"]
        | {
            p: world.digest((OUT / p).read_bytes())
            for p in (
                "scores.csv",
                "scores.json",
                "prediction-lock.json",
                "conditioning-lock.json",
                "pass-support.png",
            )
        }
    )
    save_json(OUT / "score-lock.json", dict(cases=lock["cases"], files=hashes))
    figures(panels, raw + tile, hashes)


def plot(rows):
    import matplotlib.pyplot as plt

    measured = [r for r in rows if r["arm"] == "c0" and r["method"] == trial.model.METHODS[0]]
    y = list(range(len(measured)))
    names = [
        r["id"] if r["panel"] != "waveform" else "Waveform " + r["condition"] for r in measured
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5.5), layout="constrained")
    a, b, c = axes
    a.barh(y, [r["angle_pairs"] for r in measured], color="#b4cdd1", label="Angle-eligible")
    a.scatter(
        [r["raw_inside_pairs"] for r in measured], y, marker="o", label="Raw in-box intersection"
    )
    a.scatter(
        [r["conditioned_inside_pairs"] for r in measured], y, marker="x", label="Conditioned in-box"
    )
    a.set_xscale("symlog", linthresh=1)
    a.set(title="Independent two-line proposals", xlabel="Pairs (log scale)")
    b.scatter(
        [r["median_affine_hz_per_km"] for r in measured],
        y,
        color="#922859",
        marker="D",
        label="Unknown affine receiver clock",
    )
    b.scatter(
        [r["median_offset_only_hz_per_km"] for r in measured],
        y,
        color="#236781",
        label="Unknown constant clock",
    )
    b.set(title="Profiled line strength", xlabel="Median Hz/km")
    c.scatter([r["fixed_0_held_rms_hz"] for r in measured], y, label="Tile centre")
    c.scatter([r["fixed_-8_held_rms_hz"] for r in measured], y, marker="x", label="8 km west")
    c.scatter([r["fixed_8_held_rms_hz"] for r in measured], y, marker="+", label="8 km east")
    c.set(title="Fixed-site held shape residual", xlabel="Conditional RMS (Hz)")
    for i, ax in enumerate(axes):
        ax.set(yticks=y, yticklabels=names if not i else [""] * len(names))
        ax.set_ylim(len(y) - 0.6, -0.4)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    fig.savefig(OUT / "pass-support.png", dpi=160)
    plt.close(fig)


def figures(panels, rows, frozen):
    cards = []
    for panel, queries in panels.items():
        transfer = panel != "containing"
        cases = [q["id"] for q in queries]
        file, seal = f"{panel}-positions.jsonl.gz", f"{panel}-figure-lock.json"
        files = frozen | {file: pack(OUT, file, [r for r in rows if r["id"] in cases])}
        card = dict(
            id=f"{trial.model.METHODS[0]}-{panel}",
            method=trial.model.METHODS[0],
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=f"Two-pass intersections on {panel} offers",
            caption="Continuous two-pass intersections, mirrored seeds and tile-centre prior.",
            seal=seal,
            provenance=["blind-plan.json", "prediction-lock.json", "scores.json"],
            series=[],
        )
        for key, mode, label in zip(
            ("candidate", "stock", "four") if transfer else ("one", "stock", "one_native_factors"),
            (*trial.model.METHODS, CENTER),
            ("Two-pass intersections", "Mirrored seeds", "Tile centre prior"),
            strict=True,
        ):
            line = dict(key=key, label=label, value=mode, file=file)
            if mode != trial.model.METHODS[0]:
                line["match"] = list(MATCH)
            if mode != CENTER and (transfer or mode == trial.model.METHODS[0]):
                line["forced_label"] = label + " · forced"
            card["series"].append(line)
        if transfer:
            query = f"{panel}-queries.json"
            save_json(OUT / query, dict(queries=queries))
            files[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=cases, files=files))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=1, charts=cards))


if __name__ == "__main__":
    score()
