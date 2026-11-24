"""Fit saved training inputs once and score immutable held-RF predictions later."""

import argparse
import gzip
from hashlib import sha256
import json
from math import log
import os
from pathlib import Path
import resource
import sys
from types import SimpleNamespace

from dense_family_holdout import FOLDS, GRAPH_SHA, HERE, NOMINAL, RELEASE, fold, gate, input_case, read
from dense_family_refit import ARMS, checked, clock, spent


PROTOCOL_SHA = "bd2bd6cb9f464c7d8c02b8b1f88f0e6357eaa0ec4a5b3942ad6e02304105692b"
ENROLLMENT = Path("/dev/shm/leo-0008-family-holdout01/sealed.json")
ENROLLMENT_SHA = "68a6daa4da87d10f9928e2b029a9d9c5b81eb1187d4b3293d968f4a007232d85"


def pair_for(case, nominations):
    if case == "DS30-0008":
        pair = (63478, 67511)
        anchors = [row for row in nominations if {c["norad"] for c in row["shortlist"]} == set(pair)]
        if len(anchors) != 6:
            raise ValueError("The dense training contrast no longer has its six matched arcs")
    else:
        anchors = [min((row for row in nominations if len(row["shortlist"]) == 2),
                       key=lambda row: (-row["shortlist"][1]["log_odds"], row["track"]))]
        pair = tuple(c["norad"] for c in anchors[0]["shortlist"])
    background = {}
    for row in nominations:
        choices = row["shortlist"]
        if not choices or any(c["norad"] in pair for c in choices):
            continue
        runner = choices[1]["log_odds"] if len(choices) == 2 else 0.
        if choices[0]["log_odds"] - runner >= log(10):
            background[row["track"]] = choices[0]["norad"]
    return pair, {row["track"] for row in anchors}, background


def schedule(document, rows):
    import numpy as np

    source, anchor = document["source"], document["clock_anchor"]
    origin = anchor["sample_counter"]
    sample_rate = source["sample_rate_hz"]
    times = np.array([(row["valid_start_counter"]-origin) / sample_rate + source["probe_ms"] * 0.0005
                      for row in rows])
    rf = np.array([row["actual_rf_hz"] for row in rows])
    receivers = sorted({row["receiver_id"] for row in rows})
    if len(receivers) != 2:
        raise ValueError("Expected two native receiver IDs")
    radios = np.array([receivers.index(row["receiver_id"]) + 1 for row in rows])
    return times, rf, radios


def probabilities(train, anchors):
    import numpy as np

    probes = train["source"]["probes"]
    times, rf, radio = schedule(train, probes)
    outside = np.ones(len(probes), dtype=bool)
    target = np.zeros(len(probes), dtype=bool)
    members = set()
    for arc in anchors:
        inside = (times >= arc["times"][0]) & (times <= arc["times"][-1])
        outside &= ~inside
        target |= inside & (rf == arc["rf_hz"]) & (radio == arc["receiver"])
        members.update(arc["observation_ids"])
    session = train["source"]["session_id"]
    observed = np.array(["sha256:" + sha256(
        f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode()).hexdigest() in members
        for row in probes])
    positive = np.array([any(c["passed_fractional_margin_gate"] is True for c in row["candidates"])
                         for row in probes])
    if np.any(observed & ~target):
        raise ValueError("A matched training member falls outside its signed acquisition scope")
    lam = {str(rx): (int((outside & (radio == rx) & positive).sum()) + 1)
           / (int((outside & (radio == rx)).sum()) + 2) for rx in (1, 2)}
    return dict(clutter_positive=lam, orbit_positive=(int(observed.sum()) + 1) / (int(target.sum()) + 2),
                training_open=int(target.sum()), training_matched=int(observed.sum()))


def predictive_view(p, times, rf, radio, label):
    import numpy as np

    from leo.analysis.research.retained_track_likelihood import PERIOD, projected_receiver_basis

    q = rf / 11.5e9
    hardware = np.zeros((len(times), p.hardware.shape[1]))
    smooth = np.zeros((len(times), p.smooth.shape[1]))
    # Channel 4 remains in the lower bank at both held actual RFs.
    hardware[np.arange(len(times)), 2*(radio-1)] = PERIOD / np.sqrt(12)
    hardware[np.arange(len(times)), 4+2*(radio-1)] = times - 150
    hardware[np.arange(len(times)), 5+2*(radio-1)] = -.5 * (times - 150)
    if p.fitted_c:
        hardware[:, 8] = (rf / 1e9 - 11.5) * 200000
    basis = q[:, None] * projected_receiver_basis(times)
    width = basis.shape[1]
    for rx in (1, 2):
        use = radio == rx
        smooth[use, (rx-1)*width:rx*width] = basis[use]
    return SimpleNamespace(**(vars(p) | dict(flat_times=times, flat_labels=np.full(len(times), p.labels.index(label)),
        q=q, hardware=hardware, smooth=smooth, constants=np.zeros((len(times), len(p.members))))))


def trained_forecast(scan, rows, means_by_label, model, arm, label, plan, signal_scope):
    import numpy as np
    from scipy.linalg import solve_triangular

    from leo.analysis.localization_v3 import event_position
    from leo.analysis.localization_v3.discovery import zero_state
    from leo.analysis.localization_v3.families import AnchoredFamilies
    from leo.analysis.localization_v3.predictive_linear import geometry_features

    xy = np.zeros(2)
    seed = dict(rows=rows, state=zero_state(scan))
    base = AnchoredFamilies(scan, seed, "receiver_smooth", False, xy)
    node = dict(seed=seed, aliases=base.alias)
    powers, keep = np.ones(len(base.rows)), np.ones(len(base.flat_times), bool)
    means = np.array([means_by_label[j] for j in base.labels])
    phase = means.copy()
    for _ in range(3):
        p = event_position.make_event_problem(scan, node, keep, arm, phase, powers, means, model, [])
        event_position.cached(p)
        calculation = p.calculate(xy)
        state = p.state(xy)
        phase = np.clip(state["phases"][p.labels], -15., 15.)
    features = calculation["features"]
    w = calculation["noise_precision"][p.noise_groups] / p.point_noise**2
    gram = np.diag(calculation["coefficient_prior_precision"]) + features.T @ (features * w[:, None])
    posterior = np.linalg.cholesky(gram)
    view = predictive_view(p, *plan, label)
    prediction = geometry_features(view, xy, 0.)
    features = prediction["features"]
    mean = view.q * prediction["intercept"] + features @ calculation["coefficient"]
    uncertainty = solve_triangular(posterior, features.T, lower=True)
    variance = np.sum(uncertainty**2, axis=0) + 2*scan.radio_sigma_hz**2 + 300.**2
    visible = signal_scope & (prediction["elevation"] >= 0)
    residual = calculation["conditional_residual_hz"]
    return dict(mean_hz=mean, sigma_hz=np.sqrt(variance), active=visible,
                train_count=len(base.flat_times), train_RMS_hz=float(np.sqrt(np.mean(residual**2))),
                train_objective=calculation["negative_twice_elbo"], fitted_c_hz_per_ghz=state["beta"][8] if arm == "fitted_c" else 0.,
                phase_s=float(state["phases"][label]), phase_last_change_s=float(np.max(abs(phase-p.reference))),
                design_rank=len(calculation["coefficient"]), rss_offer_center_only=True)


def check_runtime():
    from aperture_trial import THREADS
    from dense_geographic_trial import host

    machine = host()
    if not all(os.environ.get(key) == "1" for key in (*THREADS, "OMP_THREAD_LIMIT")):
        raise ValueError("Expected all six numerical thread limits")
    checked(HERE / "dense-family-holdout-offline-protocol.md", PROTOCOL_SHA)

    def no_raw(event, info):
        if event == "open" and isinstance(info[0], (str, bytes)) and (
                "fast-scan-recordings" in Path(os.fsdecode(info[0])).parts):
            raise RuntimeError("The offline study only accepts saved native packets")

    sys.addaudithook(no_raw)
    return machine


def training(case, output):
    import numpy as np
    from aperture_trial import write
    from blind_joint_finish import history_model

    from leo.analysis.localization_v3.history_position import forecast_phase_mean
    from leo.analysis.localization_v3.noise import estimate_noise
    from leo.analysis.localization_v3.phase_prior import forecast
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.retained_position import phase_widths
    from leo.analysis.localization_v3.signed_phase import adjust_means, qualify
    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.contracts.digests import canonical_digest
    from leo.operations.localization_v3_inputs import prepare_phase_history
    from tools.pipeline_eval.variants import v5_core

    now = clock()
    machine = check_runtime()
    config = TrackConfig(**read(RELEASE / "assets/tracks.json", GRAPH_SHA)["config"])
    admitted = read(ENROLLMENT, ENROLLMENT_SHA)["records"][case]
    retained = {}
    summary = gate(case, config, retained=retained)
    if any(summary[key] != admitted[key] for key in ("packet", "archive", "center", "population", "nominations")):
        raise ValueError("The training phase did not exactly reproduce the sealed nominations")
    pair, anchors, background = pair_for(case, summary["nominations"])
    tracks, sky, train = (retained[key] for key in ("tracks", "sky", "train"))
    clock_prep = spent(now)
    start = clock()
    noise = estimate_noise(tracks["tracks"], tracks["observations"])
    raw = prepare_phase_history(retained["reader"], sky["nominal_elements"], tracks["metadata"], element_parser=retained["parser"])
    prepared = dict(tracks=tracks, sky=sky, noise=noise, phase_history=raw, phase_forecast=forecast(raw))
    region = SearchRegion(summary["center"])
    scan = v5_core.scan_context(prepared, region, None, None, "genuine_previous")
    scan.curved = [i for i in scan.curved if scan.tracks[i]["key"] in anchors or scan.tracks[i]["key"] in background]
    guard = {(scan.tracks[i]["receiver"], scan.tracks[i]["rf_hz"]) for i in scan.curved}
    if any(len({rf for radio, rf in guard if radio == rx}) < 2 for rx in (1, 2)):
        raise ValueError("The blinded training layout did not cover two RFs per radio")
    model, history_valid = history_model(prepared, scan)
    prior = prepared["phase_forecast"]
    signed = qualify(prior["transitions"], prior["temporal_split_boundary_ns"], prior["prefix_distribution"], model)
    labels = {int(label): i for i, label in enumerate(scan.norads)}
    indices = sorted({labels[norad] for norad in (*pair, *background.values())})
    _, receipts = phase_widths(scan, indices)
    means = forecast_phase_mean(receipts, model["shrinkage"])
    means = dict(zip(indices, adjust_means(means, receipts, model, signed), strict=True))
    clock_nuisance_setup = spent(start)
    start = clock()
    anchor_tracks = [scan.tracks[i] for i in scan.curved if scan.tracks[i]["key"] in anchors]
    rate = probabilities(train, anchor_tracks)
    plan = schedule(train, retained["held_schedule"])
    scope = np.any([(plan[0] >= arc["times"][0]) & (plan[0] <= arc["times"][-1])
                    for arc in anchor_tracks], axis=0)
    outputs = {}
    for norad in pair:
        rows = []
        for i in scan.curved:
            key = scan.tracks[i]["key"]
            owner = norad if key in anchors else background[key]
            rows.append(dict(component=key, active_curvature=True, candidate_index=labels[owner], candidate_norad=owner))
        outputs[str(norad)] = {arm: trained_forecast(scan, rows, means, model, arm, labels[norad], plan, scope)
                               for arm in ARMS}
    clock_fit = spent(start)
    count = sum(len(scan.tracks[i]["times"]) for i in scan.curved)
    training_bytes = sum(scan.tracks[i][key].nbytes for i in scan.curved for key in ("times", "values"))
    output.mkdir()
    path = output / "forecast.json"
    write(path, dict(case=case, protocol=PROTOCOL_SHA, enrollment=ENROLLMENT_SHA, center=summary["center"],
                     packet=summary["packet"], archive=summary["archive"], fold_rf=FOLDS[case], machine=machine,
                     held_schedule_sha256=canonical_digest(retained["held_schedule"]), probabilities=rate,
                     training_sha256=canonical_digest(train["source"]["probes"]), rivals=pair,
                     fixed_calibration_arcs=len(scan.curved), matched_arcs=sorted(anchors), training_points=count,
                     retained_training_array_bytes=training_bytes, history_qualified=history_valid,
                     signed_qualified=signed["qualified"], clocks=dict(preparation=clock_prep, setup=clock_nuisance_setup,
                         fit_and_forecast=clock_fit), forecasts=outputs))
    size = path.stat().st_size
    write(output / "train-clock.json", dict(cpu_and_elapsed=spent(now), seal_sha256=sha256(path.read_bytes()).hexdigest(),
                                           peak_RSS_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                           forecast_bytes=size, position_fits=0, raw_reads=0))


def log_likelihood(positive, observed_hz, predicted_hz, sigma_hz, clutter, probability):
    import numpy as np
    from scipy.special import erf

    from leo.analysis.research.retained_track_likelihood import PERIOD

    residual = (observed_hz - predicted_hz + PERIOD/2) % PERIOD - PERIOD/2
    offsets = residual[:, None] + PERIOD * np.arange(-1, 2)
    normal = np.exp(-.5 * (offsets / sigma_hz[:, None])**2).sum(axis=1)
    normal /= sigma_hz * np.sqrt(2*np.pi) * erf(1.5*PERIOD / (np.sqrt(2)*sigma_hz))
    with_signal = probability * normal + (1-probability) * clutter / PERIOD
    return np.where(positive, np.log(with_signal), np.log((1-probability)*(1-clutter)))


def scoring(case, output):
    import numpy as np
    from aperture_trial import read as read_json, write

    from leo.contracts.digests import canonical_digest

    check_runtime()

    def one():
        begin = clock()
        publication = read_json(output / "train-clock.json")
        sealed = read(output / "forecast.json", publication["seal_sha256"])
        if (sealed["case"], sealed["protocol"], sealed["enrollment"]) != (case, PROTOCOL_SHA, ENROLLMENT_SHA):
            raise ValueError("Unexpected offline model binding")
        native, _, pin, _, _ = input_case(case)
        _, held = fold(native, sealed["fold_rf"])
        if sealed["packet"] != pin or sealed["held_schedule_sha256"] != canonical_digest(
                [{key: row[key] for key in NOMINAL} for row in held]):
            raise ValueError("Held opportunities differ from the prediction seal")
        times, _, radios = schedule(native, held)
        winner = [max((c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True),
                      key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None) for row in held]
        positive = np.array([c is not None for c in winner])
        cfo = np.array([float(c["fractional_tracking_cfo_hz"]) if c is not None else 0. for c in winner])
        rate = sealed["probabilities"]
        clutter = np.array([rate["clutter_positive"][str(radio)] for radio in radios])
        blocks = np.floor(times / 10).astype(int)
        scores = {}
        for arm in ARMS:
            hypotheses = {}
            raw = []
            for norad in map(str, sealed["rivals"]):
                prior = sealed["forecasts"][norad][arm]
                live = np.asarray(prior["active"], bool)
                terms = log_likelihood(positive, cfo, np.array(prior["mean_hz"]), np.array(prior["sigma_hz"]),
                                       clutter, live * rate["orbit_positive"])
                raw.append(terms)
                hypotheses[norad] = dict(total_nats=float(terms.sum()), signal_opportunities=int(live.sum()),
                                         signal_positive=int((live & positive).sum()), signal_empty=int((live & ~positive).sum()))
            contrast = raw[0] - raw[1]
            scores[arm] = dict(hypotheses=hypotheses, first_minus_second_nats=float(contrast.sum()),
                               positive_nats=float(contrast[positive].sum()), empty_nats=float(contrast[~positive].sum()),
                               by_radio={str(rx): float(contrast[radios == rx].sum()) for rx in (1, 2)},
                               blocks={str(k): float(contrast[blocks == k].sum()) for k in np.unique(blocks)})
        cost = spent(begin)
        return dict(rivals=sealed["rivals"], positives=int(positive.sum()), empties=int((~positive).sum()),
                    scores=scores, seal_sha256=publication["seal_sha256"]), cost

    first, start = one()
    repeat, again = one()
    if first != repeat:
        raise ValueError("Repeated held scoring must reproduce exactly")
    write(output / "held-score.json", dict(first, replay_clocks=dict(first=start, repeat=again),
          score_peak_RSS_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("train", "score"))
    parser.add_argument("case", choices=tuple(FOLDS))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"train": training, "score": scoring}[args.stage](args.case, args.output)
