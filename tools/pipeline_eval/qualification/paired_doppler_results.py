"""Score actual same-window pair geometry and the matched individual-arc control."""

import gzip
import json

from ..__main__ import encoded, save_json
from ..scoring import ARMS, ROLES, distance_km
from . import paired_doppler_geometry as geom
from . import paired_doppler_trial as trial
from . import trackless_likelihood_results as shared
from .absolute_doppler_results import MATCH
from .armijo_finish_results import pack
from .native_joint_full_results import roi_margin
from .prefix_figures import csv_file

OUT, world = trial.OUT, trial.world
CENTER = "paired_doppler_tile_center"
FIELDS = (
    "native_rf_lanes",
    "raw_probes",
    "exact_receiver_path_windows",
    "simultaneous_distinct_rf_path_windows",
    "gated_receiver_windows",
    "separated_two_peak_windows",
    "linked_arcs",
    "persistent_pairs",
    "pair_cfo_witnesses",
    "pair_rf_lanes",
    "train_pair_blocks",
    "held_pair_blocks",
    "candidate_orbit_pairs",
    "geometry_train_blocks",
    "geometry_held_blocks",
    "differential_train_rms_hz",
    "differential_held_rms_hz",
    "held_pair_families",
    "held_site_lead",
    "profiled_radius_km",
    "train_rms_hz",
    "held_rms_hz",
    "held_families",
    "c_identifiable",
)


def read_rows(name):
    with gzip.open(OUT / name, "rt") as stream:
        return list(map(json.loads, stream))


def score():
    first = world.read(OUT / "prediction-lock.json")
    second = world.read(OUT / "geometry-lock.json")
    world.verify(OUT, first["files"])
    world.verify(OUT, second["files"])
    roster = world.read(OUT / "blind-plan.json")["cases"]
    base = read_rows(trial.PREDICTIONS)
    fitted = {r["id"]: r for r in read_rows(geom.PREDICTIONS)}
    records = {(r["id"], r["method"]): r for r in base}
    if (
        set(fitted) != set(second["cases"])
        or len(records) != len(base)
        or set(records) != {(q["id"], method) for q in roster for method in trial.METHODS}
    ):
        raise ValueError("pair and shared-clock rows differ from the supported roster")
    refs, originals, omitted, wave, historic = shared.authorities()
    rows, charts, panels, terminal = [], [], {}, []
    for q in roster:
        ident, recording = q["id"], q["recording"]
        raw = records[ident, trial.METHODS[0]]
        if q["cohort"] == "generated-omitted":
            if q != trial.displacement(next(p for p in roster if p["id"] == recording)):
                raise ValueError("generated omission differs from the source-only construction")
            truth, panel, condition = refs[recording]["truth"], "generated-omitted", "omitted"
            roof, wave_scores = {}, {}
        else:
            truth, panel, condition, roof, wave_scores = shared.compare_original(
                raw, wave, omitted, refs, originals, historic
            )
        if (roi_margin(truth, q["tile"]) >= 0) != (condition == "containing"):
            raise ValueError("incorrect offer containment during post-seal audit")
        bind = {k: raw[k] for k in MATCH}
        panels.setdefault(panel, []).append(
            dict(
                id=ident,
                recording=recording,
                condition=condition,
                truth=truth,
                bindings=bind,
            )
        )
        center = q["tile"]["center"]
        charts.append(
            dict(
                raw,
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
        if raw["result"]["metrics"].get("supports_geometry") != (ident in fitted):
            raise ValueError("the earlier support gate does not match the geometry schedule")
        for method in trial.METHODS:
            r = fitted.get(ident, raw) if method == trial.METHODS[0] else records[ident, method]
            if any(r[k] != value for k, value in (q | bind).items()):
                raise ValueError("same-IQ control differs from original input or offer")
            if (
                r["id"] in fitted
                and method == trial.METHODS[0]
                and (r["support_row_sha256"] != world.digest(encoded(raw)))
            ):
                raise ValueError("a geometry fit used another exact-overlap witness set")
            value, metric = r["result"], r["result"]["metrics"]
            if method == trial.METHODS[0] and metric.get("position_attempted") is False:
                if value["status"] != "withheld" or any(
                    endpoint[k] is not None
                    for endpoint in value["arms"].values()
                    for k in ("latlon", "forced_latlon")
                ):
                    raise ValueError("invalid terminal support rejection")
                terminal.append(
                    dict(
                        id=ident,
                        method=method,
                        source_row_sha256=world.digest(encoded(r)),
                        status=value["status"],
                        reason=value["reason"],
                    )
                )
                value = value | {"metrics": metric | {"terminal_position_decision": True}}
            charts.append(dict(r, result=value))
            for arm, endpoint in value["arms"].items():
                numerical = endpoint.get("status") != "unavailable"
                report = {k: metric.get(k) for k in FIELDS}
                if not numerical:
                    for k in (
                        "differential_train_rms_hz",
                        "differential_held_rms_hz",
                        "held_pair_families",
                        "held_site_lead",
                        "profiled_radius_km",
                    ):
                        report[k] = None
                inst = wave_scores.get(arm, {})
                rows.append(
                    dict(
                        id=ident,
                        recording=recording,
                        method=method,
                        panel=panel,
                        condition=condition,
                        arm=arm,
                        status=endpoint.get("status", value["status"]),
                        reason=endpoint.get("reason", value["reason"]),
                        error_km=distance_km(endpoint["latlon"], truth),
                        forced_error_km=distance_km(endpoint["forced_latlon"], truth),
                        tile_error_km=distance_km(center, truth),
                        installed_error_km=inst.get("position_error_km"),
                        position_attempted=numerical and metric.get("position_attempted", False),
                        geometry_wall_s=r.get("geometry_wall_s") if numerical else None,
                        geometry_cpu_s=r.get("geometry_cpu_s") if numerical else None,
                        pair_cpu_s=r.get("pair_cpu_s"),
                        pair_wall_s=r.get("pair_wall_s"),
                        shared_worker_cpu_s=r.get("cpu_s"),
                        shared_worker_wall_s=r.get("native_elapsed_s"),
                        measured_peak_rss_kib=max(
                            r.get("peak_rss_kib", 0), r.get("geometry_peak_rss_kib", 0)
                        ),
                        **report,
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
    csv_file(OUT / "scores.csv", rows)
    save_json(OUT / "scores.json", dict(rows=rows))
    save_json(
        OUT / "terminal-decisions.json",
        dict(
            records=terminal,
            support_prediction_sha256=first["files"][trial.PREDICTIONS],
            geometry_prediction_sha256=second["files"][geom.PREDICTIONS],
        ),
    )
    plot(rows)
    files = (
        first["files"]
        | second["files"]
        | {
            name: world.digest((OUT / name).read_bytes())
            for name in (
                "prediction-lock.json",
                "geometry-lock.json",
                "scores.csv",
                "scores.json",
                "terminal-decisions.json",
                "paired-support.png",
            )
        }
    )
    save_json(OUT / "score-lock.json", dict(cases=first["cases"], files=files))
    make_figures(panels, charts, files)


def plot(rows):
    import matplotlib.pyplot as plt

    r = [v for v in rows if v["arm"] == "c0" and v["method"] == trial.METHODS[0]]
    y = list(range(len(r)))
    labels = [
        q["id"].replace("-paired-omitted", " omitted")
        if q["panel"] != "waveform"
        else "Waveform " + q["condition"]
        for q in r
    ]
    f, three = plt.subplots(1, 3, figsize=(14.7, 5.4), layout="constrained")
    a, b, c = three
    a.barh(
        y,
        [q["separated_two_peak_windows"] for q in r],
        color="#b4c9ca",
        label="Separated peak windows",
    )
    a.scatter([q["pair_cfo_witnesses"] for q in r], y, marker="D", label="Persistent witnesses")
    a.set(title="Measured exact simultaneity", xlabel="Native receiver windows")
    b.scatter([q["train_pair_blocks"] for q in r], y, marker="o", label="Training blocks")
    b.scatter([q["held_pair_blocks"] for q in r], y, marker="x", label="Held blocks")
    b.set(title="Independent time blocks", xlabel="Blocks with exact controls")
    c.scatter([q["profiled_radius_km"] for q in r], y, marker="D", label="Fit attempted")
    c.axvline(12.5, linestyle="--", color="#66818a", label="Publication limit")
    c.set(title="Phase-profiled geometry", xlabel="Worst-axis standard deviation (km)")
    for j, ax in enumerate(three):
        ax.set(yticks=y, yticklabels=labels if j == 0 else [""] * len(y))
        ax.invert_yaxis()
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), frameon=False)
    f.savefig(OUT / "paired-support.png", dpi=155)
    plt.close(f)


def make_figures(panels, rows, frozen):
    cards = []
    for panel, queries in panels.items():
        transfer = panel != "containing"
        ids = [q["id"] for q in queries]
        source, seal = f"{panel}-positions.jsonl.gz", f"{panel}-figure-lock.json"
        bound = frozen | {source: pack(OUT, source, [r for r in rows if r["id"] in ids])}
        titles = {
            "containing": "Simultaneous Doppler pairs on containing roof offers",
            "generated-omitted": "Simultaneous Doppler pairs on omitted offers",
            "waveform": "Simultaneous Doppler support on the emitted Qin waveform",
        }
        card = dict(
            id=f"paired_doppler-{panel}",
            method=trial.METHODS[0],
            scope="transfer" if transfer else "roof",
            title=titles[panel],
            cases=ids,
            caption="Independently displaced tiles with matched clock control."
            if panel == "generated-omitted"
            else "Exact receiver-window differences and matched individual-arc clock control.",
            seal=seal,
            provenance=["prediction-lock.json", "geometry-lock.json", "terminal-decisions.json"],
            series=[],
        )
        keys = (
            ("candidate", "stock", "four") if transfer else ("one", "stock", "one_native_factors")
        )
        for key, method, label in zip(
            keys,
            (*trial.METHODS, CENTER),
            ("Paired Doppler", "Individual-arc clock", "Tile centre"),
            strict=True,
        ):
            entry = dict(key=key, value=method, label=label, file=source)
            if method != trial.METHODS[0]:
                entry["match"] = list(MATCH)
            if method != CENTER and (transfer or method == trial.METHODS[0]):
                entry["forced_label"] = label + " · forced"
            card["series"].append(entry)
        if transfer:
            file = f"{panel}-queries.json"
            save_json(OUT / file, dict(queries=queries))
            bound[file] = world.digest((OUT / file).read_bytes())
            card["queries"] = file
        save_json(OUT / seal, dict(cases=ids, files=bound))
        cards.append(card)
    save_json(OUT / "figures.json", dict(version=2, charts=cards))


if __name__ == "__main__":
    score()
