"""Score blind clock-geometry positions and the independent timing gate."""

import gzip
import json
from statistics import median

from ..__main__ import save_json
from ..scoring import ARMS, ROLES, distance_km
from . import clock_geometry_pooled_trial as fit
from . import clock_geometry_trial as trial
from . import trackless_likelihood_results as original
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
METHOD = fit.model.METHOD
BASE = "clock_geometry_shared_clock_control"
CENTER = "clock_geometry_tile_center"
FIELDS = (
    "candidate_shapes",
    "profiled_radius_km",
    "retained_clock_direction",
    "data_only_receiver_profile_radius_km",
    "data_only_receiver_direction_fraction",
    "train_rms_hz",
    "held_rms_hz",
    "held_families",
    "held_site_lead",
    "c_identifiable",
    "c_projected_column_norm",
)


def chart_control(old):
    """Expose the historical control's single profiled fit on its identifiable arm."""
    original = old["result"]
    arms = original["arms"]
    if arms["c0"] != arms["fitted_c"]:
        raise ValueError("historical shared-clock arms no longer represent one fit")
    result = original | dict(
        metrics=original["metrics"] | {"c_identifiable": False, "c_projected_column_norm": 0.0},
        arms=dict(
            c0=arms["c0"],
            fitted_c=dict(
                status="unavailable",
                reason="constant_rf_projects_out_with_free_arc_intercepts",
                latlon=None,
                forced_latlon=None,
            ),
        ),
    )
    return old | dict(method=BASE, result=result)


def score():
    receipt = world.read(OUT / "prediction-lock.json")
    measured = world.read(OUT / "measurement-lock.json")
    world.verify(OUT, receipt["files"])
    world.verify(OUT, measured["files"])
    offers, _, earlier = trial.keys()
    refs, old, omitted, wave, installed = original.authorities()
    closure = {r["recording"]: r for r in world.read(OUT / "clock-measurements.json")["records"]}
    with gzip.open(OUT / fit.PREDICTIONS, "rt") as source:
        predictions = list(map(json.loads, source))
    results = {r["id"]: r for r in predictions}
    if len(results) != len(predictions) or set(results) != set(receipt["cases"]):
        raise ValueError("missing or ambiguous clock-coupled predictions")
    charts, scores, panels, clocks = [], [], {}, {}
    for q in offers:
        key, site = q["id"], q["recording"]
        candidate = results[key]
        baseline = chart_control(earlier[key, trial.previous.METHODS[1]])
        if any(candidate.get(k) != v or baseline.get(k) != v for k, v in q.items()):
            raise ValueError("common receiver control does not use the exact cohort request")
        bind = {k: candidate[k] for k in MATCH}
        if any(baseline.get(k) != v for k, v in bind.items()):
            raise ValueError("clock-coupled model did not receive the original request bytes")
        if q["cohort"] == "generated-omitted":
            truth, group, condition, roof, prior = refs[site]["truth"], "omitted", "omitted", {}, {}
        else:
            truth, group, condition, roof, prior = original.compare_original(
                candidate, wave, omitted, refs, old, installed
            )
        if (roi_margin(truth, q["tile"]) >= 0) != (condition == "containing"):
            raise ValueError("the measured outcome disagrees with the geometric offer class")
        if site in clocks and candidate["clock"] != clocks[site]:
            raise ValueError("a geographic offer altered site-independent clock calibration")
        clocks[site] = candidate["clock"]
        if not candidate["result"]["metrics"].get("applied_relative_bands"):
            a, b = (r["result"]["arms"]["c0"] for r in (candidate, baseline))
            if distance_km(a["forced_latlon"], b["forced_latlon"]) not in (None, 0):
                raise ValueError("unconstrained fallback changed the matched baseline")
        t = closure[site]["result"]["timing"]
        if closure[site]["native_sha256"] != q["native_sha256"]:
            raise ValueError("timing witness authority does not match the position recording")
        panels.setdefault(group, []).append(
            dict(
                id=key,
                recording=site,
                truth=truth,
                condition=condition,
                bindings=bind,
            )
        )
        center = q["tile"]["center"]
        controls = dict(
            candidate,
            method=CENTER,
            result=dict(
                status="ok",
                reason=None,
                boundary="Unconditional supplied tile centre",
                metrics={},
                arms={a: dict(latlon=center, forced_latlon=None) for a in ARMS},
            ),
        )
        charts.extend((candidate, baseline, controls))
        for r in (candidate, baseline):
            value, metric = r["result"], r["result"]["metrics"]
            for arm, ep in value["arms"].items():
                installed_result = prior.get(arm, {})
                usable = ep.get("status") != "unavailable"
                rows = {k: metric.get(k) for k in FIELDS}
                if not usable:
                    for k in (
                        "profiled_radius_km",
                        "retained_clock_direction",
                        "data_only_receiver_profile_radius_km",
                        "data_only_receiver_direction_fraction",
                        "train_rms_hz",
                        "held_rms_hz",
                        "held_families",
                        "held_site_lead",
                    ):
                        rows[k] = None
                scores.append(
                    dict(
                        id=key,
                        recording=site,
                        panel=group,
                        condition=condition,
                        method=r["method"],
                        arm=arm,
                        status=ep.get("status", value["status"]),
                        reason=ep.get("reason", value["reason"]),
                        error_km=distance_km(ep["latlon"], truth),
                        forced_error_km=distance_km(ep["forced_latlon"], truth),
                        centre_error_km=distance_km(center, truth),
                        installed_error_km=installed_result.get("position_error_km"),
                        timing_pieces=len(t["pieces"]),
                        timing_qualified_train=t["qualified_train_blocks"],
                        timing_qualified_held=t["qualified_held_blocks"],
                        calibration_cpu_s=r.get("calibration_cpu_s"),
                        calibration_wall_s=r.get("calibration_wall_s"),
                        process_cpu_s=r.get("cpu_s"),
                        wall_s=r.get("native_elapsed_s"),
                        rss_kib=r.get("peak_rss_kib"),
                        enabled_clock_bands=len(metric.get("applied_relative_bands", [])),
                        low_band_relative_hz_s=candidate["clock"]["0"].get("relative_hz_s"),
                        low_band_sigma_hz_s=candidate["clock"]["0"].get("sigma_hz_s"),
                        low_band_check_rms_hz=candidate["clock"]["0"].get("check_rms_hz"),
                        **{
                            f"timing_{k}_median_samples": median(x[k] for x in t["pieces"])
                            if t["pieces"]
                            else None
                            for k in ("physical", "reversed", "clock_only")
                        },
                        **rows,
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
    files = (
        receipt["files"]
        | measured["files"]
        | {
            f: world.digest((OUT / f).read_bytes())
            for f in (
                "prediction-lock.json",
                "scores.csv",
                "scores.json",
                "clock-geometry-support.png",
            )
        }
    )
    baseline_dir = trial.previous.OUT
    baseline_sources = {
        str((baseline_dir / f).relative_to(trial.ROOT)): world.digest(
            (baseline_dir / f).read_bytes()
        )
        for f in ("prediction-lock.json", trial.previous.PREDICTIONS)
    }
    save_json(
        OUT / "score-lock.json",
        dict(cases=receipt["cases"], files=files, historical_control_sources=baseline_sources),
    )
    figures(
        charts,
        panels,
        files | {"score-lock.json": world.digest((OUT / "score-lock.json").read_bytes())},
    )


def plot(rows):
    import matplotlib.pyplot as plt

    result = [r for r in rows if r["method"] == METHOD and r["arm"] == "c0"]
    baseline = {r["id"]: r for r in rows if r["method"] == BASE and r["arm"] == "c0"}
    y = list(range(len(result)))
    names = [
        r["id"].replace("-paired-omitted", " omitted")
        if r["panel"] != "waveform"
        else "Waveform " + r["condition"]
        for r in result
    ]
    fig, (a, b, c) = plt.subplots(1, 3, figsize=(14.5, 5.5), layout="constrained")
    for field, legend, glyph in (
        ("physical", "Physical sign", "D"),
        ("reversed", "Reversed", "x"),
        ("clock_only", "Affine only", "o"),
    ):
        a.scatter(
            [r[f"timing_{field}_median_samples"] for r in result], y, label=legend, marker=glyph
        )
    a.axvline(3, linestyle="--", color="gray", label="Timing limit")
    a.set(title="Measured frame timing closure", xlabel="Median held per-piece RMS (samples)")
    measured = [(i, r) for i, r in enumerate(result) if r["low_band_relative_hz_s"] is not None]
    b.errorbar(
        [r["low_band_relative_hz_s"] for _, r in measured],
        [i for i, _ in measured],
        xerr=[r["low_band_sigma_hz_s"] for _, r in measured],
        fmt="D",
        capsize=3,
        label="Relative drift ± uncertainty floor",
    )
    b.axvline(0, linewidth=1, color="gray")
    b.set(title="Held-qualified low-band relation", xlabel="RX1 − RX0 (Hz/s)")
    c.scatter([r["profiled_radius_km"] for r in result], y, marker="D", label="Clock constraint")
    c.scatter(
        [baseline[r["id"]]["profiled_radius_km"] for r in result],
        y,
        marker="x",
        label="Original shared clock",
    )
    c.axvline(12.5, linestyle="--", color="gray", label="Publication limit")
    c.set(title="Regional position conditioning", xlabel="Clock-profiled worst-axis σ (km)")
    for i, ax in enumerate((a, b, c)):
        ax.set(yticks=y, yticklabels=names if not i else [""] * len(y))
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    fig.savefig(OUT / "clock-geometry-support.png", dpi=155)
    plt.close(fig)


def figures(rows, panels, sealed):
    result = []
    for group, queries in panels.items():
        direct = group == "containing"
        ids = [j["id"] for j in queries]
        src, seal = f"{group}-positions.jsonl.gz", f"{group}-figure-lock.json"
        lock = sealed | {src: pack(OUT, src, [r for r in rows if r["id"] in ids])}
        card = dict(
            id=f"{METHOD}-{group}",
            method=METHOD,
            scope="roof" if direct else "transfer",
            cases=ids,
            title=f"Clock-constrained geometry on {group} offers",
            caption="Pilot clock prior and matched control. Both fits project out fixed RF c.",
            seal=seal,
            provenance=["measurement-lock.json", "prediction-lock.json", "score-lock.json"],
            series=[],
        )
        keys = ("one", "stock", "one_native_factors") if direct else ("candidate", "stock", "four")
        for key, method, name in zip(
            keys,
            (METHOD, BASE, CENTER),
            ("Clock prior", "Original clock", "Tile centre"),
            strict=True,
        ):
            line = dict(key=key, value=method, label=name, file=src)
            if method != METHOD:
                line["match"] = list(MATCH)
            if method != CENTER and (not direct or method == METHOD):
                line["forced_label"] = name + " · forced"
            card["series"].append(line)
        if not direct:
            query = f"{group}-queries.json"
            save_json(OUT / query, dict(queries=queries))
            lock[query] = world.digest((OUT / query).read_bytes())
            card["queries"] = query
        save_json(OUT / seal, dict(cases=ids, files=lock))
        result.append(card)
    save_json(OUT / "figures.json", dict(version=2, charts=result))


if __name__ == "__main__":
    score()
