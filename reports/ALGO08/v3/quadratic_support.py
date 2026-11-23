"""Fixed-observation incidence, causal acquisition opportunities and nominal geometry."""

from collections import defaultdict
from hashlib import sha256

import numpy as np


ANCHOR_SECONDS = 8.
FACTOR_FIELDS = ("integer_epoch_sample", "fractional_epoch_offset_samples", "fractional_tracking_cfo_hz")
ROLES = ("conditional", "predictive")


def native_rows(document):
    source = document["source"]
    anchor = document["clock_anchor"]["sample_counter"]
    rows = {}
    for row in source["probes"]:
        counter, receiver = row["valid_start_counter"], row["receiver_id"]
        oid = "sha256:" + sha256(f"{source['session_id']}:{receiver}:{counter}".encode()).hexdigest()
        eligible = [c for c in row["candidates"] if c["passed_fractional_margin_gate"] is True]
        measured = max(eligible, key=lambda c: (c["fractional_margin"], -c["candidate_rank"]), default=None)
        if oid in rows:
            raise ValueError("Duplicate native receiver and hardware counter")
        rows[oid] = dict(visit=row["visit_index"], counter=counter, time_s=(counter-anchor) / source["sample_rate_hz"],
                         receiver=receiver, channel=row["channel"], rf_hz=row["actual_rf_hz"],
                         signal=None if measured is None else tuple(measured[key] for key in FACTOR_FIELDS))
    return rows


def incidence(complete, sparse, full_native, paid_native, paid):
    if full_native.keys() != paid_native.keys():
        raise ValueError("Full and paid captures must keep the same timeline")
    matched_measurement = {oid for oid, row in full_native.items()
                           if row["signal"] is not None and row["signal"] == paid_native[oid]["signal"]}
    paid_stock = {oid for oid in complete if full_native[oid]["visit"] in paid}
    common = complete.keys() & sparse.keys() & matched_measurement
    paid_exact = paid_stock & matched_measurement
    if not common <= paid_exact or any(paid_native[oid]["visit"] not in paid for oid in sparse):
        raise ValueError("Paid ownership carries an unpaid observation")
    counts = dict(full=len(complete), sparse=len(sparse), unpaid=len(complete) - len(paid_stock),
                  paid_no_signal=sum(paid_native[oid]["signal"] is None for oid in paid_stock),
                  paid_changed_peak=sum(paid_native[oid]["signal"] is not None and oid not in paid_exact
                                        for oid in paid_stock),
                  paid_exact=len(paid_exact), exact_common=len(common),
                  paid_exact_unowned=len(paid_exact - sparse.keys()),
                  sparse_only_or_changed_peak=len(sparse) - len(common))
    for label in ("norad", "role", "effective_alias"):
        counts[f"changed_{label}"] = sum(complete[oid][label] != sparse[oid][label] for oid in common)
    return paid_exact, common, counts


def acquisition_ceiling(full_owners, sparse_owners, full_native, paid):
    """Score hidden owners inside independently definable paid past-anchor intervals."""
    anchors = defaultdict(list)
    for oid, owner in sparse_owners.items():
        row = full_native[oid]
        key = (owner["norad"], row["receiver"], row["channel"], row["rf_hz"])
        anchors[key].append((row["time_s"], oid))
    horizon = {key: sorted(rows) for key, rows in anchors.items()}
    groups = defaultdict(list)
    for oid, owner in full_owners.items():
        row = full_native[oid]
        if row["visit"] in paid:
            continue
        key = (owner["norad"], row["receiver"], row["channel"], row["rf_hz"])
        preceding = [(t, anchor) for t, anchor in horizon.get(key, ())
                     if 0. < row["time_s"] - t <= ANCHOR_SECONDS]
        groups[(*key, int(row["time_s"] // ANCHOR_SECONDS))].append(
            (row["time_s"], row["visit"], preceding[-2:] if len(preceding) >= 2 else ()))
    parts = []
    for key, lost in sorted(groups.items()):
        supported = sum(bool(witness) for _, _, witness in lost)
        parts.append(dict(norad=key[0], receiver=key[1], channel=key[2], rf_hz=key[3], epoch=key[4],
                          missing=len(lost), past_anchor_supported=supported,
                          missing_times_s=[t for t, _, _ in lost],
                          supported_visits=[visit for _, visit, history in lost if history]))
    return sorted(parts, key=lambda row: (-row["missing"], row["norad"], row["receiver"], row["epoch"]))


def proposals(sparse, timeline, paid):
    """Nominate unpaid family/lane queries using only paid owner rows and times."""
    by_radio = defaultdict(list)
    for oid, row in timeline.items():
        by_radio[(row["receiver"], row["channel"], row["rf_hz"])].append((row["time_s"], oid))
    opportunities = {}
    for radio in by_radio.values():
        history = []
        for time, oid in sorted(radio):
            history = [(t, label, anchor) for t, label, anchor in history if time-t <= ANCHOR_SECONDS]
            if oid in sparse:
                if timeline[oid]["visit"] not in paid:
                    raise ValueError("A nomination anchor must come from an originally paid visit")
                history.append((time, sparse[oid]["norad"], oid))
            elif timeline[oid]["visit"] not in paid:
                support = defaultdict(list)
                for t, label, anchor in history:
                    if time > t:
                        support[label].append(anchor)
                families = {label: support[label][-2:] for label in sorted(support) if len(support[label]) >= 2}
                if families:
                    opportunities[oid] = families
    return opportunities


def projected(matrix, keep=(0, 1), *, free=(), excluded=()):
    """Profile weighted nuisance using a stable augmented prior and least squares."""
    drop = {*keep, *excluded}
    nuisance_index = [i for i in range(matrix.shape[1]) if i not in drop]
    design = matrix[:, keep]
    nuisance = matrix[:, nuisance_index]
    penalty = np.diag([float(i not in free) for i in nuisance_index])
    target = np.concatenate((design, np.zeros((len(nuisance_index), len(keep)))))
    template = np.concatenate((nuisance, penalty))
    coefficient = np.linalg.lstsq(template, target, rcond=1e-11)[0]
    residual = target - template @ coefficient
    return residual.T @ residual


def eigen_data(matrix):
    eigenvalues = np.linalg.eigvalsh(matrix)
    return dict(information=matrix, weakest=float(eigenvalues[0]), strongest=float(eigenvalues[1]),
                covariance_sigma_km=float(np.sqrt(1 / eigenvalues[0])) if eigenvalues[0] > 0. else None)


def uncertainty(scan, roles):
    from arc_design import ARMS, geometry_rows

    out = {}
    for arm, (_, _, global_width, rows) in zip(ARMS, geometry_rows(scan, roles), strict=True):
        orbit = tuple(range(global_width, rows.shape[1] - len(roles)))
        fixed = projected(rows, excluded=(2,))
        clock = projected(rows, free=(2,))
        free_orbit = projected(rows, free=orbit, excluded=(2,))
        joint = projected(rows, free=(2, *orbit))
        report = dict(fixed_clock=eigen_data(fixed), profiled_clock=eigen_data(clock),
                      profiled_orbit=eigen_data(free_orbit), profiled_clock_orbit=eigen_data(joint))
        if arm == "fitted_c":
            mixed = projected(rows, (0, 1, 11), excluded=(2,))
            report["position_km_per_1000_hz_per_ghz"] = -np.linalg.solve(mixed[:2, :2], mixed[:2, 2]) / 200.
        out[arm] = report
    return out


def validation_fold(length):
    positions = np.arange(length)
    held = (positions % 3 == 1) & (positions > 0) & (positions < length - 1)
    return ~held, held


def paid_holdout(prepared, region, bound, tracks, roles):
    from arc_design import ARMS, named_rows
    from arc_design_trial import retained
    from blind_joint_finish import build_at, digest, history_model
    from blind_joint_signed import update
    from leo.analysis.localization_v3 import event_position
    from leo.analysis.localization_v3.history_policy import pair_passes
    from leo.analysis.localization_v3.tracks import active_curvature
    from tools.pipeline_eval.variants import v5_core

    included, membership, masks, evidence = [], [], [], []
    for track, role in zip(tracks, roles, strict=True):
        if role[1] != "conditional" or role[2] is None:
            continue
        train, held = validation_fold(len(track["times"]))
        if (train.sum() < 6 or held.sum() < 2 or not active_curvature(
                {key: track[key][train] for key in ("times", "values")})):
            continue
        included.append(track)
        membership.append(role)
        masks.append(train)
        evidence.append(dict(track=track["key"], train=int(train.sum()), held=int(held.sum()),
                             quadratic_training_residual_dof=int(train.sum() - 3)))
    if not masks:
        return dict(status="no_training_eligible_paid_arc", arcs=evidence)
    stage = retained(prepared, included, membership, refit=False)
    stage["noise"] = dict(constant_radio_sigma_hz=150., extra_parameter_BIC_gain=0.,
                          per_observation_noise_sigma_hz={})
    scan = v5_core.scan_context(stage, region, digest(stage["noise"]), bound, "genuine_previous")
    scan.curved = list(range(len(included)))
    node, _ = named_rows(scan, membership, predictive=True)
    keep = np.concatenate(masks)
    model, _ = history_model(stage, scan)
    zeros = {row["candidate_index"]: 0. for row in node["seed"]["rows"]}
    base, powers, means = build_at(scan, node, keep, np.zeros(2), zeros, model)
    ordinary = {arm: event_position.refit(scan, node, base.keep, arm, powers, means, model, [], [])
                for arm in ARMS}
    audit = dict(status="ordinary_training_rejected", arcs=evidence,
                 failed={arm: [r["component"] for r in fit["gates"]["tracks"] if not r["compatible"]]
                         for arm, fit in ordinary.items()})
    if not pair_passes(ordinary, half_width_km=region.half_width_km):
        return audit
    support = dict(scan=scan, node=node, keep=keep, powers=powers, means=means, model=model, arms=ordinary, entries=[])
    details = {}
    chosen = update(stage, support, details)
    scores = {}
    for arm, final in chosen["arms"].items():
        problem = event_position.make_event_problem(scan, node, keep, arm, final["phase_reference"],
                                                    powers, chosen["means"], model, [])
        residual = problem.calculate(final["endpoint_east_north_km"])["conditional_residual_hz"]
        by_track = {track["key"]: float(np.sqrt(np.mean(residual[sl][~mask] ** 2)))
                    for track, sl, mask in zip(included, problem.slices, masks, strict=True)}
        scores[arm] = dict(training_rms_hz=float(np.sqrt(np.mean(residual[keep] ** 2))),
                           held_rms_hz=float(np.sqrt(np.mean(residual[~keep] ** 2))),
                           held_track_rms_hz=by_track,
                           endpoints_km=final["endpoint_east_north_km"])
    return dict(status="validated_paid_conditional_prediction", arcs=evidence, scores=scores,
                signed_status=details["signed"]["status"])
