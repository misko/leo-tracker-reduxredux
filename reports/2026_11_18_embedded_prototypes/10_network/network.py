"""Train a small coordinate regressor on displaced synthetic Doppler scans."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from bench import CASES, PANEL, latlon
import cold_replay as cold


TRAIN = ("DS26-0002", "DS26-0004", "DS26-0006", "DS26-0010", "DS26-0012", "DS26-0018")
VALIDATION = ("DS26-0020", "DS26-0024", "DS26-0032")
LABEL = Path("/srv/bulk/leo/research/ds26-20261030/evaluation-site.json")
SEED = 261118
EXAMPLES_PER_SNAPSHOT = 48
TRACKS = 40
CANDIDATES = 12
HIDDEN = 32
LIMIT = PANEL["box_width_km"] / 2
GRID = np.stack(np.meshgrid(*(np.linspace(-LIMIT, LIMIT, 7),) * 2), axis=-1).reshape(-1, 2)
GRID_DESIGN = np.column_stack((np.ones(len(GRID)), -GRID))
FEATURES = len(GRID) + 2
PARAMETERS = (FEATURES + 1) * HIDDEN + (HIDDEN + 1) * 2
SHAPE_SCALE = cold.SHAPE_SD * np.sqrt(cold.SAMPLES)


def load_graph(case):
    return cold.read(cold.GRAPHS / f"{case}.json")


def sampled(document, limit):
    tracks = document["tracks"]
    order = sorted(document["curved_indices"], key=lambda i: -len(tracks[i]["times"]))
    for i in order[:limit]:
        track = tracks[i]
        if len(track["times"]) < cold.SAMPLES:
            continue
        ix = np.rint(np.linspace(0, len(track["times"]) - 1, cold.SAMPLES)).astype(int)
        yield track, ix, np.asarray(track["times"])[ix]


def centered(x):
    return x - x.mean(axis=-1, keepdims=True)


def nominate(bank, track, t, observed):
    visible = cold.interpolate(bank["up"], t, bank).min(axis=1) >= -.008
    ix = np.flatnonzero(visible)
    if not len(ix):
        return None
    ratio = track["rf_hz"] / cold.CARRIER
    f, e, n, h = [
        centered(cold.interpolate(bank[k][ix], t, bank) * ratio)
        for k in ("f", "east", "north", "rate")
    ]
    raw = np.stack((centered(observed)[None, :] - f, e, n, h), axis=1)
    normal = raw @ raw.transpose(0, 2, 1) / SHAPE_SCALE**2
    phase = normal[:, 3, 3] + cold.PHASE_SD_S**-2
    cross = normal[:, :3, 3]
    marginal = normal[:, :3, :3] - cross[:, :, None] * cross[:, None, :] / phase[:, None, None]
    order = np.argsort(marginal[:, 0, 0], kind="stable")[:CANDIDATES]
    return marginal[order], raw[order], bank["ids"][ix[order]], int(len(ix))


def scores(marginal, design):
    return np.maximum(0., np.einsum("ki,nij,kj->nk", design, marginal, design))


def evidence(document, bank, c_hz_per_ghz=0.):
    rows = []
    for track, ix, t in sampled(document, TRACKS):
        y = np.asarray(track["values"])[ix]
        if c_hz_per_ghz:
            y = y + c_hz_per_ghz * (track["rf_hz"] / 1e9 - 11.5)
            y = y - cold.PERIOD * np.rint(y[0] / cold.PERIOD)
        row = nominate(bank, track, t, y)
        if row is not None:
            rows.append(row)
    if len(rows) < 4:
        return None
    loss = np.stack([scores(marginal, GRID_DESIGN).min(axis=0) for marginal, *_ in rows])
    field = (1 / (1 + loss / 4.)).mean(axis=0)
    contrast = field - field.mean()
    x = np.r_[contrast / max(np.linalg.norm(contrast), 1e-8), field.max(), 10 * np.ptp(field)]
    return x, field, rows


def weights(theta):
    a = FEATURES * HIDDEN
    b = a + HIDDEN
    c = b + 2 * HIDDEN
    return theta[:a].reshape(FEATURES, HIDDEN), theta[a:b], theta[b:c].reshape(HIDDEN, 2), theta[c:]


def predict(theta, features):
    w1, b1, w2, b2 = weights(theta)
    return LIMIT * np.clip(np.tanh(features @ w1 + b1) @ w2 + b2, -1., 1.)


def fit(x, xy):
    rng = np.random.default_rng(SEED)
    y = xy / LIMIT
    reg = .004
    initial = rng.normal(0., .05, PARAMETERS)

    def objective(theta):
        w1, b1, w2, b2 = weights(theta)
        hidden = np.tanh(x @ w1 + b1)
        error = hidden @ w2 + b2 - y
        delta_y = error / len(x)
        delta_h = delta_y @ w2.T * (1 - hidden * hidden)
        gradient = np.r_[(x.T @ delta_h).ravel(), delta_h.sum(axis=0),
                         (hidden.T @ delta_y).ravel(), delta_y.sum(axis=0)]
        return .5 * (np.sum(error**2) / len(x) + reg * (theta @ theta)), gradient + reg * theta

    solution = minimize(objective, initial, jac=True, method="L-BFGS-B",
                        options=dict(maxiter=160, ftol=1e-10))
    if not np.isfinite(solution.fun):
        raise ValueError("Non-finite model loss")
    return solution.x.astype(np.float32), dict(iterations=solution.nit,
                                               converged=bool(solution.success),
                                               message=str(solution.message),
                                               regularized_loss=float(solution.fun))


def simulate(case, graph, bank, snapshot, rng):
    meta = graph["metadata"]
    tle = next((cold.INPUT / case / "tle").rglob(snapshot))
    catalog = cold.parse_element_sets(tle.read_text())
    lookup = {sat.satnum: sat for sat in catalog.satellites}
    satellites = [lookup[int(i)] for i in bank["ids"]]
    schedules = []
    for track, _, t in sampled(graph, 88):
        ups = cold.interpolate(bank["up"], t[[0, len(t) // 2, -1]], bank)
        visible = np.flatnonzero(ups.min(axis=1) > np.sin(np.deg2rad(12)))
        if len(visible):
            schedules.append((track, t, visible))
    if len(schedules) < TRACKS:
        raise ValueError(f"{case} has only {len(schedules)} usable synthetic schedules")
    # One visit per cell on an 8x6 geographic design, independently jittered in each snapshot.
    tile = np.stack(np.meshgrid(np.arange(8), np.arange(6)), axis=-1).reshape(-1, 2)
    xy = LIMIT * (2 * (tile + rng.random((EXAMPLES_PER_SNAPSHOT, 2))) / [8, 6] - 1)
    rng.shuffle(xy)
    for position in xy:
        lane_offset = rng.uniform(-12000., 12000., 4)
        lane_drift = rng.normal(0., 1.5, 4)
        phases = rng.normal(0., .65, len(satellites))
        c = rng.uniform(-20000., 20000.)
        generated = []
        curved = []
        for i in rng.choice(len(schedules), size=TRACKS, replace=False):
            template, t, visible = schedules[i]
            j = int(rng.choice(visible))
            g = 2 * (template["receiver"] - 1) + int(template["channel"] > 4)
            rf = template["rf_hz"]
            tau = phases[j]
            err, p, v = cold.state([satellites[j]], meta["anchor_utc_ns"], t + tau)
            if np.any(err):
                continue
            f = cold.projection(p, v, position)[0][0] * (rf / cold.CARRIER)
            u = (t - t.mean()) / np.ptp(t)
            y = (f + lane_offset[g] + lane_drift[g] * (t - 150.) + c * (rf / 1e9 - 11.5)
                 + rng.normal(0., 55., len(t)) + rng.normal(0., 120.) * u
                 + rng.normal(0., 240.) * u**2)
            if rng.random() < .2:
                y += rng.uniform(-7000., 7000.) * u + rng.uniform(-14000., 14000.) * u**2
            y -= cold.PERIOD * np.rint(y[0] / cold.PERIOD)
            residual = centered(y) - u * ((u @ centered(y)) / (u @ u))
            if np.sqrt(np.mean(residual**2)) >= 250.:
                curved.append(len(generated))
            generated.append(dict(times=t, values=y, rf_hz=rf))
        block = evidence(dict(tracks=generated, curved_indices=curved), bank)
        if block is None:
            raise ValueError(f"{case} synthetic example lacked sufficient tracks")
        x, field, _ = block
        yield x, position, GRID[np.argmax(field)]


def synthetic_split(cases):
    X, y, peak, receipts = [], [], [], []
    for case in cases:
        graph = load_graph(case)
        meta = graph["metadata"]
        bank, receipt = cold.build_bank(case, meta, check_approximation=False)
        cut = meta["causal_cutoff_utc_ns"]
        receipts.append(dict(case=case, scan_open_utc_ns=cut,
                             scan_end_utc_ns=int(cut + round(meta["duration_s"] * 1e9)),
                             snapshot=receipt["snapshot"], examples=EXAMPLES_PER_SNAPSHOT))
        rng = np.random.default_rng(SEED + int(case[-4:]))
        for x, xy, grid_peak in simulate(case, graph, bank, receipt["snapshot"], rng):
            X.append(x)
            y.append(xy)
            peak.append(grid_peak)
    return np.asarray(X), np.asarray(y), np.asarray(peak), receipts


def distribution(x):
    arr = np.asarray(x, dtype=float)
    return dict(n=len(arr), median=float(np.median(arr)), p95=float(np.percentile(arr, 95)),
                maximum=float(np.max(arr)))


def distance(query, ref):
    a, b = np.deg2rad(query)
    c, d = np.deg2rad(ref)
    h = np.sin((a - c) / 2)**2 + np.cos(a) * np.cos(c) * np.sin((b - d) / 2)**2
    return float(12742.0176 * np.arcsin(np.sqrt(h)))


def shape_rms(xy, rows):
    design = np.r_[1., -xy]
    ms, chosen_ids = [], []
    for marginal, raw, ids, _ in rows:
        best = int(np.argmin(scores(marginal, design[None, :])[:, 0]))
        e, ge, gn, h = raw[best]
        delta = e - ge * xy[0] - gn * xy[1]
        tau = (delta @ h) / (h @ h + SHAPE_SCALE**2 / cold.PHASE_SD_S**2)
        ms.append(np.mean((delta - tau * h)**2))
        chosen_ids.append(ids[best])
    return float(np.sqrt(np.mean(ms))), len(set(chosen_ids))


def real_case(case, model):
    start = time.monotonic()
    graph = load_graph(case)
    read_end = time.monotonic()
    meta = graph["metadata"]
    bank, receipt = cold.build_bank(case, meta, check_approximation=False)
    bank_end = time.monotonic()
    found = evidence(graph, bank)
    evidence_end = time.monotonic()
    out = dict(case=case, bank=receipt, scan_open_utc_ns=meta["causal_cutoff_utc_ns"],
               scan_duration_s=meta["duration_s"], available_curved_tracks=len(graph["curved_indices"]))
    if found is None:
        arm = dict(status="abstain", reason="fewer_than_four_tracks_with_visible_candidates")
        out.update(wall_s=evidence_end - start, arms=dict(c0=arm, fitted_c=arm))
        return out, None
    x, field, rows = found
    start_model = time.monotonic()
    xy = predict(model, x.astype(np.float32))
    end_model = time.monotonic()
    rms, families = shape_rms(xy, rows)
    end = time.monotonic()
    arm = dict(status="estimate", latlon=latlon(xy), xy_km=xy.tolist(), rms_hz=rms,
               rms_kind="in_sample_demeaned_all_nominated_tracks", satellite_families=families,
               clipped=bool(np.max(np.abs(xy)) >= LIMIT))
    out.update(wall_s=end - start, arms=dict(c0=arm, fitted_c=arm),
               stage_s=dict(graph_read=read_end - start, causal_tle_and_sgp4=bank_end - read_end,
                            candidates_and_shape_map=evidence_end - bank_end,
                            forward_pass=end_model - start_model, rf_diagnostic=end - end_model),
               tracks=len(rows), candidates_examined=sum(row[3] for row in rows),
               map_candidate_scores=len(GRID) * sum(len(row[0]) for row in rows),
               grid_peak_latlon=latlon(GRID[np.argmax(field)]),
               feature_range=dict(peak=float(field.max()), contrast=float(np.ptp(field))))
    sensitivity = []
    for c in (-200000., 200000.):
        xx, _, shifted_rows = evidence(graph, bank, c)
        bumped = predict(model, xx.astype(np.float32))
        shifted_rms, _ = shape_rms(bumped, shifted_rows)
        dx = float(np.max(np.abs(x - xx)))
        shift_km = float(np.linalg.norm(xy - bumped))
        drift_hz = abs(rms - shifted_rms)
        assert dx < 1e-8 and shift_km < 1e-4 and drift_hz < .01
        sensitivity.append(dict(injected_c_hz_per_ghz=c, feature_max_abs_delta=dx,
                                displacement_km=shift_km, rms_delta_hz=drift_hz))
    out["sensitivity"] = sensitivity
    return out, x


def correctness_check():
    rng = np.random.default_rng(SEED)
    raw = rng.normal(size=(8, 4, cold.SAMPLES)) * 100.
    m = raw @ raw.transpose(0, 2, 1) / SHAPE_SCALE**2
    denominator = m[:, 3, 3] + cold.PHASE_SD_S**-2
    cross = m[:, :3, 3]
    reduced = m[:, :3, :3] - cross[:, :, None] * cross[:, None, :] / denominator[:, None, None]
    explicit = []
    for v in GRID_DESIGN:
        r = v @ raw[:, :3, :]
        h = raw[:, 3, :]
        tau = (r * h).sum(axis=1) / (SHAPE_SCALE**2 * denominator)
        explicit.append((((r - tau[:, None] * h)**2).sum(axis=1) / SHAPE_SCALE**2)
                        + (tau / cold.PHASE_SD_S)**2)
    residual = float(np.max(np.abs(scores(reduced, GRID_DESIGN) - np.array(explicit).T)))
    assert residual < 1e-12
    theta = rng.normal(size=PARAMETERS).astype(np.float32)
    x = rng.normal(size=(5, FEATURES)).astype(np.float32)
    assert np.allclose(predict(theta, x), np.stack([predict(theta, j) for j in x]), atol=2e-5)
    return dict(profiled_cost_max_abs_error=residual, single_vs_batch_forward_check=True)


def main(output):
    test = correctness_check()
    start = time.monotonic()
    train_x, train_y, _, train = synthetic_split(TRAIN)
    train_features_s = time.monotonic() - start
    train_start = time.monotonic()
    model, optimizer = fit(train_x, train_y)
    fit_s = time.monotonic() - train_start
    val_start = time.monotonic()
    val_x, val_y, val_peak, validation = synthetic_split(VALIDATION)
    val_features_s = time.monotonic() - val_start
    predict_val = predict(model, val_x.astype(np.float32))
    val_shift = np.roll(predict_val, EXAMPLES_PER_SNAPSHOT, axis=0)
    val_controls = {
        name: distribution(np.linalg.norm(position - val_y, axis=1))
        for name, position in dict(network=predict_val, shape_grid_peak=val_peak,
                                   no_radio_center=np.zeros_like(val_y), mismatched_maps=val_shift).items()
    }
    rows, all_x = map(list, zip(*(real_case(case, model) for case in CASES), strict=True))
    partitions = [
        {r["snapshot"].split("-")[1] for r in train},
        {r["snapshot"].split("-")[1] for r in validation},
        {r["bank"]["snapshot"].split("-")[1] for r in rows},
    ]
    assert sum(map(len, partitions)) == len(set.union(*partitions))
    assert max(r["scan_end_utc_ns"] for r in train) < min(r["scan_open_utc_ns"] for r in validation)
    assert max(r["scan_end_utc_ns"] for r in validation) < min(r["scan_open_utc_ns"] for r in rows)
    ready = [(row, x) for row, x in zip(rows, all_x, strict=True) if x is not None]
    if ready:
        x = ready[0][1].astype(np.float32)
        forward_start = time.monotonic()
        for _ in range(1000):
            predict(model, x)
        forward_mean_us = (time.monotonic() - forward_start) * 1e3
    else:
        forward_mean_us = None
    # Evaluation begins here. No geographic DS26 label flows into fitting, feature
    # generation, synthetic validation, calibration sensitivity, or RF diagnostics.
    ref_data = cold.read(LABEL)
    ref = [ref_data["latitude_deg"], ref_data["longitude_deg"]]
    memorizer = np.mean(np.array([ref]), axis=0)
    controls = dict(network=[], shape_grid_peak=[], no_radio_center=[],
                    mismatched_maps=[], shared_site_no_radio_memorizer=[])
    for j, (row, _) in enumerate(ready):
        alt = ready[(j + 1) % len(ready)][0]["arms"]["c0"]["latlon"]
        errors = dict(network=distance(row["arms"]["c0"]["latlon"], ref),
                      shape_grid_peak=distance(row["grid_peak_latlon"], ref),
                      no_radio_center=distance(PANEL["search_center_latlon"], ref),
                      mismatched_maps=distance(alt, ref),
                      shared_site_no_radio_memorizer=distance(memorizer, ref))
        row["evaluation_only_errors_km"] = errors
        for name, err in errors.items():
            controls[name].append(err)
    model_path = output.with_name("weights.npy")
    np.save(model_path, model, allow_pickle=False)
    record = dict(
        method="synthetic-trained tiny coordinate network from anonymous shape-only Doppler",
        timing_scope="scan close; per case reads and parses archived graph, fresh causal TLE read "
                     "and SGP4, candidates, 49-cell shape map, float32 network, and RF diagnostic; "
                     "excludes precomputed graph construction, training, sensitivity and scoring",
        cases=rows,
        checks=dict(correctness=test, seed=SEED, training_snapshots=train, validation_snapshots=validation,
                    snapshot_content_disjoint=True, optimizer=optimizer,
                    calibration="Stationary c times RF offset is constant within a single-channel "
                                "track. The shape features remove every track mean before nomination "
                                "and fitting. Both arms are the same estimator, and no c was fitted.",
                    synthetic_validation_error_km=val_controls,
                    synthetic_train_error_km=distribution(
                        np.linalg.norm(predict(model, train_x.astype(np.float32)) - train_y, axis=1)),
                    ds26_evaluation_error_km={k: distribution(v) if v else None for k, v in controls.items()},
                    label_control="Single shared campaign reference assigned to DS26-0002 after "
                                  "model inference and used to fit a constant two-coordinate output. "
                                  "This intentionally reuses the geography of the test scans.",
                    model=dict(layers=[FEATURES, HIDDEN, 2], parameters=PARAMETERS,
                               float32_weight_bytes=model.nbytes,
                               float_multiply_accumulates_per_pass=FEATURES * HIDDEN + 2 * HIDDEN,
                               single_case_repeated_mean_forward_us=forward_mean_us,
                               sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                               train_feature_wall_s=train_features_s, training_wall_s=fit_s,
                               validation_feature_wall_s=val_features_s)
                    ))
    output.write_text(json.dumps(record, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--check", action="store_true")
    cli.add_argument("--output", type=Path, default=HERE / "result.json")
    options = cli.parse_args()
    if options.check:
        print(json.dumps(correctness_check(), indent=2))
    else:
        main(options.output)
