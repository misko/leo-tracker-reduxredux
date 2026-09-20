"""Matched local replay of historical/current Doppler cohorts; no evaluation site input.

Identities remain frozen from their explicitly labelled parent experiments.
Every new fit uses randomized partitions, and starts at a parent's wide-search mode.
"""

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json
from scipy.optimize import least_squares

from leo.analysis.research.doppler_error_budget import profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_sets


def fitting_weights(data, weighting):
    """Equal total fitting weight per selected unit; evaluation adds no weight."""
    if weighting == "observation":
        return np.ones(len(data["segment"]))
    if weighting == "segment":
        units = data["segment"]
    elif weighting == "pass":
        units = data["pass_group"]
    else:
        raise ValueError("unknown fitting weight unit")
    _, group = np.unique(units, return_inverse=True)
    count = np.bincount(group[data["training"].astype(bool)], minlength=group.max() + 1)
    if np.any(count == 0):
        raise ValueError("every weight unit needs fitting observations")
    return 1 / np.sqrt(count[group])


def extract(root, assignments, clock_s=0.0):
    arrays = {
        k: [] for k in ("y", "segment", "training", "p", "v", "episode", "norad", "session", "time")
    }
    docs, cats, sources, records = {}, {}, {}, []
    segment_offset = 0
    for i, a in enumerate(assignments):
        sid = a["session_id"]
        path = root / "evidence" / (sid + ".json")
        if sid not in docs:
            doc = json.loads(path.read_text())
            doc["inventory"]["partition"] = "randomized"
            docs[sid] = doc
            sources[str(path)] = digest(path)
        doc = docs[sid]
        arc = dict(load_observations(doc, 0))[a["episode_id"]]
        meta = doc["inventory"]
        path = root / "evidence" / meta["tle_file"]
        if str(path) not in cats:
            cat = parse_element_sets(path.read_text())
            cats[str(path)] = (cat, {n: j for j, n in enumerate(cat.satellite_numbers)})
            sources[str(path)] = digest(path)
        if sources[str(path)] != meta["tle_digest"]:
            raise ValueError("TLE digest mismatch")
        cat, ids = cats[str(path)]
        p, v, valid = state_arrays(
            cat, [ids[a["norad"]]], meta["reference_utc_ns"], arc.time_s, clock_s=clock_s
        )
        if len(valid) != 1:
            raise ValueError("invalid selected orbit")
        n = len(arc.time_s)
        for shift in [-0.5, 0.5]:
            pp, vv, good = state_arrays(
                cat,
                [ids[a["norad"]]],
                meta["reference_utc_ns"],
                arc.time_s,
                clock_s=clock_s + shift,
            )
            if len(good) != 1:
                raise ValueError("invalid timing sensitivity orbit")
            for name, value in [(f"p{shift}", pp[0]), (f"v{shift}", vv[0])]:
                arrays.setdefault(name, []).extend(value)
        values = dict(
            y=arc.frequency_hz,
            segment=arc.segment + segment_offset,
            training=arc.training,
            p=p[0],
            v=v[0],
            episode=np.full(n, i),
            norad=np.full(n, a["norad"]),
            session=np.full(n, list(docs).index(sid)),
            time=arc.time_s,
        )
        for k, value in values.items():
            arrays[k].extend(value)
        segment_offset += len(np.unique(arc.segment))
        records.append(dict(**a, observations=n, span_s=float(np.ptp(arc.time_s))))
    return {k: np.asarray(v) for k, v in arrays.items()}, dict(sources=sources, records=records)


def fit(
    data,
    region,
    initial,
    weighting,
    robust,
    subset=None,
    fit_clock=False,
    clock_groups=None,
    fit_height=False,
):
    mask = np.ones(len(data["y"]), bool) if subset is None else subset
    d = {k: v[mask] for k, v in data.items()}
    train = d["training"].astype(bool)
    _, group = np.unique(d["segment"], return_inverse=True)
    counts = np.bincount(group[train])
    weight = fitting_weights(d, weighting)
    if clock_groups is not None and not fit_clock:
        raise ValueError("clock groups require clock fitting")
    labels, clock_index = np.unique(
        np.zeros(len(group), int) if clock_groups is None else np.asarray(clock_groups)[mask],
        return_inverse=True,
    )

    clock_start = 3 if fit_height else 2

    def residual(x):
        receiver = region.points([x[0]], [x[1]], x[2] * 1000 if fit_height else 0).ecef_km[0]
        p, v = d["p"], d["v"]
        if fit_clock:
            # Quadratic interpolation of exact propagated states over +/-0.5 s.
            # Bound the clock to that interval; not an extrapolating orbit model.
            tau = np.asarray(x[clock_start:])[clock_index, None]
            p = (
                p
                + (d["p0.5"] - d["p-0.5"]) * tau
                + 2 * (d["p0.5"] + d["p-0.5"] - 2 * p) * tau * tau
            )
            v = (
                v
                + (d["v0.5"] - d["v-0.5"]) * tau
                + 2 * (d["v0.5"] + d["v-0.5"] - 2 * v) * tau * tau
            )
        delta = p - receiver
        predicted = (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * v, axis=1)
            / np.linalg.norm(delta, axis=1)
        )
        return profile(d["y"] - predicted, group, train)

    def objective(x):
        r = residual(x)
        if robust:
            r = r * np.sqrt(2 / (np.sqrt(1 + (r / 250) ** 2) + 1))
        return (r * weight)[train]

    lower = [-region.width_km / 2, -region.height_km / 2]
    upper = [region.width_km / 2, region.height_km / 2]
    start = list(initial)
    if fit_height:
        lower.append(-0.5)
        upper.append(5.0)
        start.append(0.0)
    if fit_clock:
        lower.extend([-0.5] * len(labels))
        upper.extend([0.5] * len(labels))
        start.extend([0.0] * len(labels))
    answer = least_squares(
        objective,
        start,
        bounds=(lower, upper),
        diff_step=1e-6,
        xtol=1e-11,
        ftol=1e-11,
        gtol=1e-6,
        max_nfev=100,
    )
    r = residual(answer.x)
    lat, lon = region.coordinates(*answer.x[:2])
    segment_rms = {
        str(k): float(np.sqrt(np.mean(r[(group == k) & train] ** 2))) for k in np.unique(group)
    }
    return dict(
        x_km=answer.x.tolist(),
        latitude_deg=float(lat),
        longitude_deg=float(lon),
        altitude_m=float(answer.x[2] * 1000) if fit_height else 0.0,
        height_fitted=fit_height,
        height_at_bound=bool(fit_height and (answer.x[2] < -0.499 or answer.x[2] > 4.999)),
        training_rms_hz=float(np.sqrt(np.mean(r[train] ** 2))),
        evaluation_rms_hz=float(np.sqrt(np.mean(r[~train] ** 2))),
        weighting=weighting,
        robust=robust,
        observations=len(group),
        source_segments=len(counts),
        episodes=len(np.unique(d["episode"])),
        converged=bool(answer.success),
        clock_s=(float(answer.x[clock_start]) if len(labels) == 1 else None) if fit_clock else 0.0,
        clock_group_values=labels.tolist() if fit_clock else [],
        clock_offsets_s=answer.x[clock_start:].tolist() if fit_clock else [],
        clock_fitted=fit_clock,
        clock_at_bound=bool(fit_clock and np.any(abs(answer.x[clock_start:]) > 0.499)),
        segment_training_rms=segment_rms,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in [
        "historical-root",
        "blind-polish",
        "wide-run",
        "current-states",
        "current-polish",
        "output",
    ]:
        parser.add_argument("--" + key, type=Path, required=True)
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    old = json.loads(a.blind_polish.read_text())
    wide = json.loads((a.wide_run / "result.json").read_text())
    longitudinal = json.loads((a.historical_root / "longitudinal.json").read_text())
    conditional = []
    for row in longitudinal["positioning"]:
        if row["included"]:
            conditional.extend(
                dict(session_id=row["session_id"], episode_id=e, norad=n)
                for e, n in zip(row["episode_ids"], row["norads"], strict=True)
            )
    cohorts = {}
    for name, assignments in [
        ("historical_site_selected", conditional),
        ("historical_wide_selected", old["assignments"]),
    ]:
        d, provenance = extract(a.historical_root, assignments)
        np.savez_compressed(a.output / (name + ".npz"), **d)
        write_json(a.output / (name + "-inputs.json"), provenance)
        cohorts[name] = (d, Region(**old["region"]), [wide["east_km"], wide["north_km"]])
    current = json.loads(a.current_polish.read_text())
    d = dict(np.load(a.current_states))
    d["p"], d["v"], d["episode"] = d["p0.0"], d["v0.0"], d["segment"]
    d = {
        k: d[k]
        for k in [
            "y",
            "segment",
            "training",
            "p",
            "v",
            "episode",
            "norad",
            "session",
            "time",
            "p0.5",
            "v0.5",
            "p-0.5",
            "v-0.5",
        ]
    }
    cohorts["current_fov_selected"] = (
        d,
        Region(**current["region"]),
        current["models"][0]["position_km"],
    )
    output = {
        "identity_provenance": {
            "historical_site_selected": "Known-site candidate selection; NOT blind",
            "historical_wide_selected": (
                "Historical broad-region identity selection; new local fit only"
            ),
            "current_fov_selected": (
                "Broad-region search with known-site-derived FoV; NOT independent blind"
            ),
        },
        "partition": "randomized",
        "evaluation_site_used_in_fitting": False,
        "cohorts": {},
        "source_digests": {
            str(p): digest(p)
            for p in [
                a.blind_polish,
                a.current_polish,
                a.current_states,
                a.wide_run / "result.json",
            ]
        },
    }
    for name, (d, region, initial) in cohorts.items():
        rows = []
        for weighting in ["observation", "segment"]:
            for robust in [False, True]:
                row = fit(d, region, initial, weighting, robust)
                rows.append(row)
                print(
                    name,
                    weighting,
                    robust,
                    row["latitude_deg"],
                    row["longitude_deg"],
                    row["evaluation_rms_hz"],
                    flush=True,
                )
        for weighting in ["observation", "segment"]:
            row = fit(d, region, initial, weighting, True, fit_clock=True)
            rows.append(row)
            print(
                name,
                "joint UTC",
                weighting,
                row["clock_s"],
                row["latitude_deg"],
                row["longitude_deg"],
                flush=True,
            )
        output["cohorts"][name] = dict(region=vars(region), initial=initial, models=rows)
        write_json(a.output / "results.json", output)


if __name__ == "__main__":
    main()
