"""Decompose archived TLE updates at common times; retrospective diagnostic only."""

import argparse
import json
from pathlib import Path

import numpy as np
from replay_regional_doppler import digest, load_observations, write_json
from scipy.optimize import least_squares

from leo.analysis.research.doppler_error_budget import profile
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ
from leo.sky.frames import (
    geodetic_to_ecef_km,
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets


def raw_state(cat, epoch_ns, times):
    jd, fraction = julian_day_from_utc_ns(
        epoch_ns + np.rint(np.asarray(times) * 1e9).astype(np.int64)
    )
    error, p, v = cat.satellites[0].sgp4_array(jd, fraction)
    if np.any(error) or not np.all(np.isfinite(p)) or not np.all(np.isfinite(v)):
        raise ValueError("invalid state")
    return p, v


def rtn_basis(p, v):
    r = p / np.linalg.norm(p, axis=1)[:, None]
    n = np.cross(p, v)
    n = n / np.linalg.norm(n, axis=1)[:, None]
    t = np.cross(n, r)
    return np.stack([r, t, n], axis=2)


def corrected_rtn(p, v, q, qd, coefficient, rate, elapsed):
    correction = coefficient + np.asarray(elapsed)[:, None] * rate
    return (
        p + np.einsum("nij,nj->ni", q, correction),
        v + np.einsum("nij,nj->ni", qd, correction) + np.einsum("nij,j->ni", q, rate),
    )


def doppler(p, v, utc_ns, receiver):
    jd, fr = julian_day_from_utc_ns(utc_ns)
    pp, vv = teme_to_ecef(p, v, greenwich_mean_sidereal_time_rad(jd, fr))
    delta = pp - receiver
    return (
        -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * vv, axis=1) / np.linalg.norm(delta, axis=1)
    )


def rms(value):
    return float(np.sqrt(np.mean(np.asarray(value) ** 2)))


def model_residual(data, model):
    tau = model["clock_s"]
    p = (
        data["p"]
        + (data["p0.5"] - data["p-0.5"]) * tau
        + 2 * (data["p0.5"] + data["p-0.5"] - 2 * data["p"]) * tau * tau
    )
    v = (
        data["v"]
        + (data["v0.5"] - data["v-0.5"]) * tau
        + 2 * (data["v0.5"] + data["v-0.5"] - 2 * data["v"]) * tau * tau
    )
    x = geodetic_to_ecef_km(model["latitude_deg"], model["longitude_deg"], 0)
    delta = p - x
    prediction = (
        -REFERENCE_RF_HZ / LIGHT_KM_S * np.sum(delta * v, axis=1) / np.linalg.norm(delta, axis=1)
    )
    return profile(data["y"] - prediction, data["segment"], data["training"])


def state_elements(p, v):
    mu = 398600.4418
    radius = np.linalg.norm(p)
    h = np.cross(p, v)
    return dict(
        a_km=float(1 / (2 / radius - np.dot(v, v) / mu)),
        e_vector=np.cross(v, h) / mu - p / radius,
        normal=h / np.linalg.norm(h),
    )


def analyze_update(old, new, epoch, times, training, segment, y, receiver):
    p, v = raw_state(old, epoch, times)
    pn, vn = raw_state(new, epoch, times)
    q = rtn_basis(p, v)
    qd = (
        rtn_basis(*raw_state(old, epoch, times + 0.25))
        - rtn_basis(*raw_state(old, epoch, times - 0.25))
    ) / 0.5
    delta = pn - p
    local = np.einsum("nji,nj->ni", q, delta)
    center = float(np.mean(times[training]))
    elapsed = times - center
    const = local[training].mean(axis=0)
    linear = np.linalg.lstsq(
        np.column_stack([np.ones(training.sum()), elapsed[training]]), local[training], rcond=None
    )[0]
    initial = float(np.sum(delta[training] * v[training]) / np.sum(v[training] ** 2))
    initial = float(np.clip(initial, -119.9, 119.9))
    phase = least_squares(
        lambda z: (raw_state(old, epoch, times[training] + z[0])[0] - pn[training]).ravel(),
        [initial],
        bounds=([-120], [120]),
        diff_step=1e-4,
    )
    affine = least_squares(
        lambda z: (
            raw_state(old, epoch, times[training] + z[0] + z[1] * elapsed[training])[0]
            - pn[training]
        ).ravel(),
        [phase.x[0], 0],
        bounds=([-120, -0.02], [120, 0.02]),
        diff_step=1e-4,
        x_scale=[1, 0.001],
    )

    def predict(name, t):
        pp, vv = raw_state(old, epoch, t)
        if name == "phase1":
            return raw_state(old, epoch, t + phase.x[0])
        if name == "phase_rate2":
            pp, vv = raw_state(old, epoch, t + affine.x[0] + affine.x[1] * (t - center))
            return pp, vv * (1 + affine.x[1])
        qq = rtn_basis(pp, vv)
        dd = (
            rtn_basis(*raw_state(old, epoch, t + 0.25))
            - rtn_basis(*raw_state(old, epoch, t - 0.25))
        ) / 0.5
        return corrected_rtn(
            pp,
            vv,
            qq,
            dd,
            const if name == "rtn3" else linear[0],
            np.zeros(3) if name == "rtn3" else linear[1],
            t - center,
        )

    utc = epoch + np.rint(times * 1e9).astype(np.int64)
    old_pred = doppler(p, v, utc, receiver)
    new_pred = doppler(pn, vn, utc, receiver)
    baseline = profile(new_pred - old_pred, segment, training)
    jacobian = []
    for axis in range(3):
        shift = np.zeros(3)
        shift[axis] = 0.01
        pp, vv = corrected_rtn(p, v, q, qd, shift, np.zeros(3), np.zeros(len(times)))
        column = profile((doppler(pp, vv, utc, receiver) - old_pred) / 0.01, segment, training)
        jacobian.append(column[training])
    singular_values = np.linalg.svd(np.column_stack(jacobian), compute_uv=False)
    te = ~training
    held_p = float(np.sqrt(np.mean(np.sum(delta[te] ** 2, axis=1))))
    base_hz = rms(baseline[te])
    long_t = np.linspace(center - 300, center + 300, 61)
    lp, lv = raw_state(new, epoch, long_t)
    models = {}
    plot_data = dict(
        time_s=times.tolist(),
        training=training.tolist(),
        old_residual_hz=profile(y - old_pred, segment, training).tolist(),
        new_residual_hz=profile(y - new_pred, segment, training).tolist(),
        orbit_mismatch_hz=baseline.tolist(),
        model_mismatch_hz={},
    )
    for name in ["phase1", "phase_rate2", "rtn3", "rtn6"]:
        pp, vv = predict(name, times)
        prediction = doppler(pp, vv, utc, receiver)
        mismatch = rms(profile(new_pred - prediction, segment, training)[te])
        measured = rms(profile(y - prediction, segment, training)[te])
        plot_data["model_mismatch_hz"][name] = profile(
            new_pred - prediction, segment, training
        ).tolist()
        poserr = float(np.sqrt(np.mean(np.sum((pp[te] - pn[te]) ** 2, axis=1))))
        xp, xv = predict(name, long_t)
        models[name] = dict(
            position_rms_m=poserr * 1000,
            position_energy_explained=1 - (poserr / max(held_p, 1e-12)) ** 2,
            orbit_doppler_mismatch_hz=mismatch,
            orbit_doppler_energy_explained=1 - (mismatch / max(base_hz, 1e-12)) ** 2,
            measured_heldout_rms_hz=measured,
            window_600s_position_rms_m=float(np.sqrt(np.mean(np.sum((xp - lp) ** 2, axis=1))))
            * 1000,
        )
    mid = np.array([center])
    mp, mv = raw_state(old, epoch, mid)
    np_, nv = raw_state(new, epoch, mid)
    oe, ne = state_elements(mp[0], mv[0]), state_elements(np_[0], nv[0])
    sat0, sat1 = old.satellites[0], new.satellites[0]
    return dict(
        rtn_mean_km=local.mean(axis=0).tolist(),
        rtn_position_energy_fraction=(
            np.sum(local**2, axis=0) / max(np.sum(local**2), 1e-20)
        ).tolist(),
        raw_position_rms_m=held_p * 1000,
        raw_velocity_rms_m_s=float(np.sqrt(np.mean(np.sum((vn - v) ** 2, axis=1)))) * 1000,
        phase_s=float(phase.x[0]),
        phase_converged=bool(phase.success),
        phase_at_bound=bool(abs(phase.x[0]) > 119.99),
        affine_phase_s=float(affine.x[0]),
        affine_rate_ppm=float(affine.x[1] * 1e6),
        affine_converged=bool(affine.success),
        rtn_constant_km=const.tolist(),
        rtn_rate_m_s=(linear[1] * 1000).tolist(),
        plane_change_deg=float(
            np.rad2deg(np.arccos(np.clip(np.dot(oe["normal"], ne["normal"]), -1, 1)))
        ),
        common_epoch_delta_a_m=(ne["a_km"] - oe["a_km"]) * 1000,
        common_epoch_delta_e_vector_norm=float(np.linalg.norm(ne["e_vector"] - oe["e_vector"])),
        raw_mean_motion_change_rev_day=float((sat1.no_kozai - sat0.no_kozai) * 1440 / (2 * np.pi)),
        bstar_before=float(sat0.bstar),
        bstar_after=float(sat1.bstar),
        mean_eccentricity_before=float(sat0.ecco),
        mean_eccentricity_after=float(sat1.ecco),
        raw_inclination_change_deg=float(np.rad2deg(sat1.inclo - sat0.inclo)),
        rtn_doppler_jacobian_singular_values_hz_per_km=singular_values.tolist(),
        baseline_orbit_doppler_mismatch_hz=base_hz,
        plot_data=plot_data,
        models=models,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for k in ["causal", "retrospective", "parent", "evidence", "output"]:
        parser.add_argument("--" + k, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    parent = json.loads((args.parent / "inference.json").read_text())
    cj = json.loads((args.causal / "strict-inference.json").read_text())
    rj = json.loads((args.retrospective / "reassociated-inference.json").read_text())
    crows = json.loads((args.causal / "strict-reranking.json").read_text())["rows"]
    rrows = json.loads((args.retrospective / "full-reranking.json").read_text())["rows"]
    lookups = [{(r["session_id"], r["episode_id"]): r for r in rs} for rs in [crows, rrows]]
    cd = dict(np.load(args.causal / "strict-states.npz"))
    rd = dict(np.load(args.retrospective / "reassociated-states.npz"))
    for k in ["y", "episode", "segment", "training", "time"]:
        if not np.array_equal(cd[k], rd[k]):
            raise ValueError("observation identity/order mismatch")
    if cj["parent_digest"] != rj["parent_digest"] or cj["parent_digest"] != digest(
        args.parent / "inference.json"
    ):
        raise ValueError("parent mismatch")
    models = [
        next(
            m
            for m in j["models"]
            if m["selection"] == "all" and m["clock_model"] == "shared_recorded"
        )
        for j in [cj, rj]
    ]
    errors = [model_residual(d, m) for d, m in zip([cd, rd], models, strict=True)]
    receivers = [geodetic_to_ecef_km(m["latitude_deg"], m["longitude_deg"], 0) for m in models]
    rows = []
    for i, assignment in enumerate(parent["assignments"]):
        key = (assignment["session_id"], assignment["episode_id"])
        oldrow, newrow = [lookup[key] for lookup in lookups]
        mask = cd["episode"] == i
        train = cd["training"][mask].astype(bool)
        times = cd["time"][mask]
        seg = cd["segment"][mask]
        y = cd["y"][mask]
        old, new = [parse_element_sets(row["winning_tle_text"]) for row in [oldrow, newrow]]
        epoch = oldrow["capture_start_utc_ns"]
        document = json.loads((args.evidence / "evidence" / (key[0] + ".json")).read_text())
        arc = dict(load_observations(document, 0))[key[1]]
        if not (
            document["inventory"]["reference_utc_ns"] == epoch
            and arc.partition == "randomized"
            and np.array_equal(arc.time_s, times)
            and np.array_equal(arc.frequency_hz, y)
            and np.array_equal(arc.training, train)
        ):
            raise ValueError("RF evidence/epoch/partition mismatch")
        for catalogue, source in [(old, oldrow), (new, newrow)]:
            if list(catalogue.satellite_numbers) != [source["best_norad"]]:
                raise ValueError("element identity mismatch")
        utc = epoch + np.rint(times * 1e9).astype(np.int64)
        op, ov = raw_state(old, epoch, times)
        np_, nv = raw_state(new, epoch, times)
        a, b = [rms(e[mask][~train]) for e in errors]
        controls = []
        for site, x in zip(["causal_position", "retrospective_position"], receivers, strict=True):
            old_r = rms(profile(y - doppler(op, ov, utc, x), seg, train)[~train])
            new_r = rms(profile(y - doppler(np_, nv, utc, x), seg, train)[~train])
            controls.append(dict(site=site, old_rms_hz=old_r, new_rms_hz=new_r))
        changed = oldrow["best_norad"] != newrow["best_norad"]
        identical = oldrow["winning_tle_text"] == newrow["winning_tle_text"]
        material = a - b >= 20 and b <= 0.75 * a
        row = dict(
            index=i,
            **assignment,
            causal_norad=oldrow["best_norad"],
            retrospective_norad=newrow["best_norad"],
            identity_changed=changed,
            identical_tle=identical,
            observations=int(mask.sum()),
            span_s=float(np.ptp(times)),
            pipeline_causal_heldout_hz=a,
            pipeline_retrospective_heldout_hz=b,
            material_improvement=material,
            causal_age_h=(epoch - old.element_epoch_utc_ns()[0]) / 3.6e12,
            retrospective_age_h=(epoch - new.element_epoch_utc_ns()[0]) / 3.6e12,
            controls=controls,
            causal_tle=oldrow["winning_tle_text"],
            retrospective_tle=newrow["winning_tle_text"],
        )
        if material and not changed and not identical:
            row["geometry"] = analyze_update(old, new, epoch, times, train, seg, y, receivers[0])
        rows.append(row)
        if i % 50 == 0:
            print(i, len(parent["assignments"]), flush=True)
    output = dict(
        diagnostic_uses_future_orbits=True,
        position_truth_used=False,
        material_rule="held-out RMS reduction >=20 Hz and >=25%; descriptive, not a p-value",
        causal_digest=digest(args.causal / "strict-inference.json"),
        retrospective_digest=digest(args.retrospective / "reassociated-inference.json"),
        rows=rows,
    )
    write_json(args.output / "analysis.json", output)
    print(
        "complete", len(rows), "material", sum(r["material_improvement"] for r in rows), flush=True
    )


if __name__ == "__main__":
    main()
