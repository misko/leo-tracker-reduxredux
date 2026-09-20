"""Reproducible, conditional error budget for the frozen 48-hour Doppler study.

This is a local audit with frozen candidate identities, not a new blind search.
No acquisition, production writes, or chronological evaluation partitions.
"""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from replay_regional_doppler import digest, load_observations, state_arrays, write_json
from scipy.optimize import least_squares

from leo.analysis.research.doppler_error_budget import information, profile, profile_shared_drift
from leo.analysis.research.regional_doppler import LIGHT_KM_S, REFERENCE_RF_HZ, Region
from leo.sky.propagation import parse_element_sets


def prepare(evidence, polish, output):
    parent = json.loads(polish.read_text())
    records, docs, catalogues = [], {}, {}
    arrays = {
        k: [] for k in ["y", "time", "training", "segment", "session", "norad", "rate", "lane"]
    }
    source_digests = {}
    start = None
    for i, a in enumerate(parent["assignments"]):
        sid = a["session_id"]
        path = evidence / "evidence" / (sid + ".json")
        if sid not in docs:
            docs[sid] = json.loads(path.read_text())
            source_digests[str(path)] = digest(path)
        doc = docs[sid]
        meta = doc["inventory"]
        if meta["partition"] != "randomized":
            raise ValueError("randomized evidence required")
        arc = dict(load_observations(doc, 0))[a["episode_id"]]
        if len(np.unique(arc.segment)) != 1:
            raise ValueError("this audit expects one source segment per assignment")
        series = next(s for s in doc["series"] if s["tracklet_id"] == a["episode_id"])
        if start is None:
            start = meta["reference_utc_ns"]
        path = evidence / "evidence" / meta["tle_file"]
        if meta["tle_digest"] != a["tle_digest"] or digest(path) != a["tle_digest"]:
            raise ValueError("frozen catalogue digest mismatch")
        if str(path) not in catalogues:
            cat = parse_element_sets(path.read_text())
            catalogues[str(path)] = (cat, {n: k for k, n in enumerate(cat.satellite_numbers)})
        n = len(arc.time_s)
        for key, value in dict(
            y=arc.frequency_hz,
            time=(meta["reference_utc_ns"] - start) / 1e9 + arc.time_s,
            training=arc.training,
            segment=np.full(n, i),
            session=np.full(n, list(docs).index(sid)),
            norad=np.full(n, a["norad"]),
            rate=np.full(n, meta["sample_rate_hz"]),
            lane=np.full(n, series["channel"] * 2 + (series["edge"] == "upper")),
        ).items():
            arrays[key].extend(value)
        records.append(
            dict(
                session_id=sid,
                episode_id=a["episode_id"],
                norad=a["norad"],
                reference_ns=meta["reference_utc_ns"],
                time_s=arc.time_s.tolist(),
                path=str(path),
                collected_ns=meta["tle_collected_ns"],
            )
        )
    data = {k: np.asarray(v) for k, v in arrays.items()}
    data["training"] = data["training"].astype(bool)
    # A pass is a fixed-identity cluster with no >120 s gap between observed supports.
    pass_groups = np.zeros(len(records), int)
    ends, group_count = {}, 0
    for i in sorted(range(len(records)), key=lambda j: np.min(data["time"][data["segment"] == j])):
        mask = data["segment"] == i
        begin, end = np.min(data["time"][mask]), np.max(data["time"][mask])
        norad = records[i]["norad"]
        if norad not in ends or begin - ends[norad][0] > 120:
            group_count += 1
            ends[norad] = (end, group_count - 1)
        else:
            ends[norad] = (max(end, ends[norad][0]), ends[norad][1])
        pass_groups[i] = ends[norad][1]
    data["pass_group"] = pass_groups[data["segment"]]
    for clock in [-2.0, -1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0, 2.0]:
        p, v = [], []
        for r in records:
            cat, ids = catalogues[r["path"]]
            pp, vv, valid = state_arrays(
                cat, [ids[r["norad"]]], r["reference_ns"], np.asarray(r["time_s"]), clock_s=clock
            )
            if len(valid) != 1:
                raise ValueError("invalid frozen satellite")
            p.extend(pp[0])
            v.extend(vv[0])
        tag = str(clock)
        data["p" + tag], data["v" + tag] = np.array(p), np.array(v)
        print("propagated UTC correction", clock, flush=True)
    snapshots = sorted({(r["collected_ns"], r["path"]) for r in records})
    alt_p, alt_v = data["p0.0"].copy(), data["v0.0"].copy()
    alt_records = []
    for i, r in enumerate(records):
        original, numbers = catalogues[r["path"]]
        original_epoch = original.element_epoch_utc_ns()[numbers[r["norad"]]]
        for collected, path in reversed(snapshots):
            if collected >= r["collected_ns"]:
                continue
            cat, ids = catalogues[path]
            if r["norad"] not in ids:
                continue
            epoch = cat.element_epoch_utc_ns()[ids[r["norad"]]]
            if epoch >= original_epoch or epoch >= r["reference_ns"]:
                continue
            pp, vv, valid = state_arrays(
                cat, [ids[r["norad"]]], r["reference_ns"], np.array(r["time_s"])
            )
            if len(valid) != 1:
                continue
            alt_p[data["segment"] == i], alt_v[data["segment"] == i] = pp[0], vv[0]
            alt_records.append(
                dict(
                    segment=i,
                    old_path=path,
                    nominal_path=r["path"],
                    epoch_difference_hours=(original_epoch - epoch) / 3.6e12,
                )
            )
            break
    data["alternate_p"], data["alternate_v"] = alt_p, alt_v
    data["alternate_available"] = np.isin(data["segment"], [r["segment"] for r in alt_records])
    np.savez_compressed(output / "states.npz", **data)
    write_json(
        output / "inputs.json",
        dict(
            records=records,
            source_digests=source_digests,
            tle_digests={p: digest(Path(p)) for p in catalogues},
            parent_digest=digest(polish),
            alternate_records=alt_records,
            reference_ns=start,
            conditional_identities=True,
            pass_gap_seconds=120,
        ),
    )
    return data


def run(data, output):
    # Truth is explicit for synthetic generation and error reporting, never an optimizer target.
    reference = (37.858988, -122.478103)
    region = Region(*reference, 200, 200)
    y, train, segment = data["y"], data["training"], data["segment"]
    times, passes = data["time"], data["pass_group"]
    n = len(y)
    p, v = data["p0.0"], data["v0.0"]

    def prediction(x, pp=p, vv=v):
        receiver = region.points([x[0]], [x[1]]).ecef_km[0]
        delta = pp - receiver
        return (
            -REFERENCE_RF_HZ
            / LIGHT_KM_S
            * np.sum(delta * vv, axis=1)
            / np.linalg.norm(delta, axis=1)
        )

    def fit(
        values=y,
        pp=p,
        vv=v,
        mask=None,
        groups=segment,
        drift=False,
        robust=True,
        initial=(3.0, 3.0),
    ):
        use = np.ones(n, bool) if mask is None else np.asarray(mask, bool)
        _, g = np.unique(groups[use], return_inverse=True)
        count = np.bincount(g[train[use]])
        weights = 1 / np.sqrt(count[g])

        def residual(x):
            if drift == "session":
                return profile_shared_drift(
                    (values - prediction(x, pp, vv))[use],
                    g,
                    data["session"][use],
                    train[use],
                    times[use],
                )
            return profile(
                (values - prediction(x, pp, vv))[use], g, train[use], times[use] if drift else None
            )

        def objective(x):
            r = residual(x)
            if robust:
                # Stable pseudo-Huber transform; same source-balanced objective as original polish.
                r = r * np.sqrt(2 / (np.sqrt(1 + (r / 250) ** 2) + 1))
            return (r * weights)[train[use]]

        result = least_squares(
            objective,
            initial,
            bounds=(-99.0, 99.0),
            diff_step=1e-4,
            xtol=1e-10,
            ftol=1e-10,
            gtol=1e-7,
            max_nfev=80,
        )
        r = residual(result.x)
        lat, lon = region.coordinates(*result.x)

        def balanced(part):
            return float(np.sqrt(np.mean([np.mean(r[(g == k) & part] ** 2) for k in np.unique(g)])))

        return dict(
            x_km=result.x.tolist(),
            latitude_deg=float(lat),
            longitude_deg=float(lon),
            reference_distance_m=float(np.linalg.norm(result.x) * 1000),
            train_rms_hz=float(np.sqrt(np.mean(r[train[use]] ** 2))),
            evaluation_rms_hz=float(np.sqrt(np.mean(r[~train[use]] ** 2))),
            segment_balanced_train_rms_hz=balanced(train[use]),
            segment_balanced_evaluation_rms_hz=balanced(~train[use]),
            tracks=int(len(np.unique(segment[use]))),
            observations=int(use.sum()),
            converged=bool(result.success),
            at_bound=bool(np.any(abs(result.x) > 98.9)),
        )

    result = dict(
        conditional_on_frozen_identities=True,
        reference_for_evaluation=reference,
        baseline=fit(),
        experiments={},
        bounds={},
        injections={},
        subsets={},
    )
    print("baseline", result["baseline"], flush=True)
    baseline_x = np.array(result["baseline"]["x_km"])
    # Solver self-consistency, not independent verification of orbit/frame conventions.
    rng = np.random.default_rng(20260920)
    truth = np.array([0.0, 0.0])
    synthetic = prediction(truth) + rng.normal(0, 20000, segment.max() + 1)[segment]
    result["synthetic_exact"] = fit(synthetic, initial=(20.0, -15.0))
    for sigma in [10, 60, 165]:
        rows = [fit(synthetic + rng.normal(0, sigma, n)) for _ in range(32)]
        result["experiments"]["synthetic_noise_" + str(sigma)] = rows
    raw_j = np.column_stack(
        [
            (
                prediction(baseline_x + np.eye(2)[k] * 0.01)
                - prediction(baseline_x - np.eye(2)[k] * 0.01)
            )
            / 0.02
            for k in range(2)
        ]
    )
    all_train = np.ones(n, bool)
    j = profile(raw_j, segment, all_train)
    for sigma in [10, 60, 165]:
        result["bounds"][str(sigma)] = information(j, sigma)
        fit_j = profile(raw_j, segment, train)[train]
        result["bounds"]["training_only_" + str(sigma)] = information(fit_j, sigma)
        weight = 1 / np.bincount(segment[train])[segment[train]]
        hessian = fit_j.T @ (weight[:, None] * fit_j)
        inv = np.linalg.inv(hessian)
        covariance = inv @ (fit_j.T @ (weight[:, None] ** 2 * fit_j)) @ inv * sigma**2
        result["bounds"]["source_balanced_training_" + str(sigma)] = dict(
            horizontal_rms_m=float(np.sqrt(np.trace(covariance)) * 1000)
        )
    result["bounds"]["free_segment_drift_60"] = information(
        profile(raw_j, segment, all_train, times), 60
    )
    result["bounds"]["known_offsets_60"] = information(raw_j, 60)
    clock_derivative = (
        prediction(baseline_x, data["p0.25"], data["v0.25"])
        - prediction(baseline_x, data["p-0.25"], data["v-0.25"])
    ) / 0.5
    # Position columns are Hz/km; clock column is Hz/s.
    clock_j = profile(clock_derivative, segment, all_train)
    augmented = np.column_stack([j, clock_j])
    normal = augmented.T @ augmented / 60**2
    cov = np.linalg.inv(normal)
    result["bounds"]["unknown_shared_utc_60"] = dict(
        horizontal_rms_m=float(np.sqrt(np.trace(cov[:2, :2])) * 1000),
        clock_sigma_s=float(np.sqrt(cov[2, 2])),
    )
    for clock in [-2.0, -1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0, 2.0]:
        result["experiments"]["utc_" + str(clock)] = fit(
            pp=data["p" + str(clock)], vv=data["v" + str(clock)]
        )
    result["experiments"]["segment_drift"] = fit(drift=True)
    result["experiments"]["session_drift"] = fit(drift="session")
    result["experiments"]["least_squares"] = fit(robust=False)
    finite_difference_velocity = (data["p0.25"] - data["p-0.25"]) / 0.5
    result["experiments"]["position_derivative_velocity"] = fit(vv=finite_difference_velocity)
    velocity_delta = profile(
        prediction(baseline_x, p, finite_difference_velocity) - prediction(baseline_x),
        segment,
        all_train,
    )
    result["velocity_convention_shape_rms_hz"] = float(np.sqrt(np.mean(velocity_delta**2)))
    # Shared offset within a pass is an intentionally strong diagnostic hypothesis.
    result["experiments"]["shared_pass_offset"] = fit(groups=passes)
    lane_pass = passes * 100 + data["lane"]
    result["experiments"]["shared_pass_lane_offset"] = fit(groups=lane_pass)
    alternative = data["alternate_available"]
    if alternative.any():
        result["experiments"]["nominal_orbit_paired_subset"] = fit(mask=alternative)
        result["experiments"]["earlier_orbit_paired_subset"] = fit(
            pp=data["alternate_p"], vv=data["alternate_v"], mask=alternative
        )
        delta = profile(
            prediction(baseline_x, data["alternate_p"], data["alternate_v"])
            - prediction(baseline_x),
            segment,
            all_train,
        )
        result["alternate_orbit_shape_rms_hz"] = float(np.sqrt(np.mean(delta[alternative] ** 2)))
    # Disturbance amplitudes are controlled scenarios, NOT estimates of real errors.
    dt = profile(times, segment, all_train)
    for shift in [0.25, 0.5]:
        generated = prediction(truth, data["p" + str(shift)], data["v" + str(shift)])
        result["injections"]["utc_" + str(shift)] = fit(generated)
    unit_drift = rng.normal(0, 1, passes.max() + 1)[passes]
    for amplitude in [1.0, 10.0]:
        drift = unit_drift * amplitude
        result["injections"]["pass_drift_hz_s_" + str(amplitude)] = fit(synthetic + drift * dt)
    perturb = rng.normal(size=(passes.max() + 1, 3))
    perturb /= np.linalg.norm(perturb, axis=1)[:, None]
    result["injections"]["orbit_position_100m"] = fit(
        prediction(truth, p + 0.1 * perturb[passes], v)
    )
    # Linearized pass-cluster sandwich: accounts for correlated residuals, not unknown bias.
    r = profile(y - prediction(baseline_x), segment, train)
    jt = profile(raw_j, segment, train)[train]
    counts = np.bincount(segment[train])
    weight = 1 / counts[segment[train]]
    z = r[train] / 250
    h = jt.T @ ((weight / (1 + z * z) ** 1.5)[:, None] * jt)
    scores = np.array(
        [
            np.bincount(passes[train], weights=weight * jt[:, k] * r[train] / np.sqrt(1 + z * z))
            for k in range(2)
        ]
    ).T
    sandwich = np.linalg.inv(h) @ (scores.T @ scores) @ np.linalg.inv(h)
    result["cluster_scatter"] = dict(
        horizontal_rms_m=float(np.sqrt(np.trace(sandwich)) * 1000),
        covariance_m2=(sandwich * 1e6).tolist(),
        independent_pass_clusters=len(scores),
    )
    draws = rng.normal(size=(500, len(scores))) @ scores @ np.linalg.inv(h)
    result["linearized_pass_multiplier_scatter_m"] = (draws * 1000).tolist()
    spans = np.array([np.ptp(times[segment == i]) for i in range(segment.max() + 1)])
    for minimum in [7, 15, 30, 45]:
        mask = spans[segment] >= minimum
        if len(np.unique(segment[mask])) >= 3:
            result["subsets"]["minimum_span_" + str(minimum)] = fit(mask=mask)
    for rate in np.unique(data["rate"]):
        result["subsets"]["rate_" + str(int(rate))] = fit(mask=data["rate"] == rate)
    for fold in range(8):
        result["subsets"]["leave_pass_fold_" + str(fold)] = fit(mask=passes % 8 != fold)
    per_track = []
    for i in range(segment.max() + 1):
        mask = segment == i
        rr = r[mask]
        order = np.argsort(times[mask])
        z = rr[order]
        per_track.append(
            dict(
                segment=i,
                pass_group=int(passes[mask][0]),
                span_s=float(spans[i]),
                rms_hz=float(np.sqrt(np.mean(rr**2))),
                information_trace=float(np.sum(j[mask] ** 2)),
                lag1_correlation=float(np.corrcoef(z[:-1], z[1:])[0, 1]),
            )
        )
    result["track_diagnostics"] = per_track
    result["counts"] = dict(
        tracks=segment.max().item() + 1,
        observations=n,
        pass_clusters=len(np.unique(passes)),
        pass_lane_groups=len(np.unique(lane_pass)),
        earlier_tle_tracks=len(np.unique(segment[alternative])),
    )
    write_json(output / "results.json", result)
    plots(result, output)
    print("complete", result["counts"], flush=True)


def plots(r, output):
    plt.rcParams.update({"axes.grid": True, "grid.alpha": 0.2, "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    sigmas = [10, 60, 165]
    axes[0].plot(
        sigmas,
        [r["bounds"][str(s)]["horizontal_rms_m"] for s in sigmas],
        "o-",
        label="Ideal IID bound; offsets unknown",
    )
    axes[0].plot(
        sigmas,
        [r["bounds"]["source_balanced_training_" + str(s)]["horizontal_rms_m"] for s in sigmas],
        "o-",
        label="Source-balanced training estimator prediction",
    )
    axes[0].plot(
        sigmas,
        [
            np.sqrt(
                np.mean(
                    [
                        a["reference_distance_m"] ** 2
                        for a in r["experiments"]["synthetic_noise_" + str(s)]
                    ]
                )
            )
            for s in sigmas
        ],
        "o-",
        label="32 nonlinear synthetic fits / level",
    )
    axes[0].set(
        xlabel="Injected independent frequency noise (Hz RMS)",
        ylabel="Horizontal RMS position error (m)",
    )
    axes[0].legend(fontsize=8)
    a = np.array(r["linearized_pass_multiplier_scatter_m"])
    axes[1].scatter(a[:, 0], a[:, 1], s=5, alpha=0.3)
    axes[1].set(
        xlabel="East perturbation (m)",
        ylabel="North perturbation (m)",
        title=(
            "Local pass-cluster scatter about fitted position\n"
            "Does not include common bias or identity uncertainty"
        ),
    )
    fig.suptitle("Conditional precision: exact geometry and frozen candidate identities")
    fig.savefig(output / "01-noise-and-pass-scatter.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    shifts = [-2.0, -1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0, 2.0]
    fits = [r["experiments"]["utc_" + str(s)] for s in shifts]
    for field, label in [
        ("train_rms_hz", "Randomized fitting"),
        ("evaluation_rms_hz", "Randomized evaluation"),
    ]:
        axes[0].plot(shifts, [a[field] for a in fits], "o-", label=label)
    axes[0].set(xlabel="Applied UTC correction (s)", ylabel="Residual RMS (Hz)")
    axes[0].legend()
    axes[1].plot(shifts, [a["reference_distance_m"] for a in fits], "o-")
    axes[1].set(
        xlabel="Applied UTC correction (s)", ylabel="Distance from configured coordinate (m)"
    )
    fig.suptitle("Exact propagated UTC sensitivity; location and segment offsets refitted")
    fig.savefig(output / "02-utc-sensitivity.png", dpi=160)
    plt.close(fig)
    names = [
        "baseline",
        "segment_drift",
        "session_drift",
        "shared_pass_offset",
        "shared_pass_lane_offset",
        "least_squares",
        "nominal_orbit_paired_subset",
        "earlier_orbit_paired_subset",
    ]
    entries = [
        (name, r["baseline"] if name == "baseline" else r["experiments"].get(name))
        for name in names
    ]
    entries = [(name, a) for name, a in entries if a]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), layout="constrained")
    labels = [name.replace("_", " ") for name, a in entries]
    for ax, field, label in zip(
        axes,
        ["evaluation_rms_hz", "reference_distance_m"],
        ["Evaluation RMS (Hz)", "Distance from configured coordinate (m)"],
        strict=True,
    ):
        ax.barh(labels, [a[field] for name, a in entries])
        ax.set_xlabel(label)
        ax.invert_yaxis()
        for row, (_, entry) in enumerate(entries):
            value = entry[field]
            xpos = min(value+12, 650) if field == 'evaluation_rms_hz' else value+100
            ax.text(xpos, row, f'{value:,.0f}', va='center', fontsize=8)
    axes[0].set_xlim(0, 1300)
    axes[0].set_title('Shared-pass outlier clipped; exact value labelled')
    axes[1].set_xlim(0, 18500)
    fig.suptitle("Model sensitivity: lower frequency residual need not mean better location")
    fig.savefig(output / "03-model-and-orbit-sensitivity.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    rows = r["track_diagnostics"]
    axes[0].scatter(
        [a["span_s"] for a in rows], [a["information_trace"] for a in rows], s=10, alpha=0.5
    )
    axes[0].set(xlabel="Track span (s)", ylabel="Local information trace (Hz²/km²)", yscale="log")
    for name, a in r["subsets"].items():
        if name.startswith("minimum_span") or name.startswith("rate_"):
            axes[1].scatter(*a["x_km"], label=name.replace("_", " "))
    axes[1].scatter(0, 0, marker="*", s=100, c="black", label="Configured coordinate")
    axes[1].set(xlabel="East from configured coordinate (km)", ylabel="North (km)")
    axes[1].legend(fontsize=8)
    fig.suptitle("Longer arcs and sample-rate sensitivity; fixed catalogue identities")
    fig.savefig(output / "04-duration-and-subsets.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--polish", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-states", action="store_true")
    a = parser.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    if a.reuse_states:
        saved = json.loads((a.output / "inputs.json").read_text())
        if saved["parent_digest"] != digest(a.polish):
            raise ValueError("parent changed")
        for path, expected in (saved["source_digests"] | saved["tle_digests"]).items():
            if digest(Path(path)) != expected:
                raise ValueError("frozen input changed: " + path)
        previous_manifest = json.loads((a.output / "sha256.json").read_text())
        if (
            hashlib.sha256((a.output / "states.npz").read_bytes()).hexdigest()
            != previous_manifest["states.npz"]
        ):
            raise ValueError("cached states changed")
        data = dict(np.load(a.output / "states.npz"))
    else:
        if (a.output / "states.npz").exists():
            raise ValueError("use fresh output or explicitly reuse frozen states")
        data = prepare(a.evidence, a.polish, a.output)
    run(data, a.output)
    write_json(
        a.output / "sha256.json",
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(a.output.iterdir())
            if p.is_file() and p.name != "sha256.json"
        },
    )


if __name__ == "__main__":
    main()
