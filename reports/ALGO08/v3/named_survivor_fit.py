"""Run the released signed numerical finish on a currently accepted fixed roster."""

from contextlib import contextmanager
from hashlib import sha256
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np


ARMS = ("c0", "fitted_c")


def now():
    return process_time(), perf_counter()


def clock(start):
    return dict(cpu_s=process_time()-start[0], elapsed_s=perf_counter()-start[1])


def fingerprint(*arrays):
    result = []
    for value in arrays:
        a = np.asarray(value)
        result.append([a.dtype.str, a.shape, sha256(a.tobytes(order="C")).hexdigest()])
    return result


def fit_record(record):
    return dict(
        position=record["endpoint_east_north_km"], latlon=record["endpoint_latlon"],
        rf_rms_hz=record["RMS_hz"], objective=record["negative_twice_elbo"],
        rf_nuisance=record["state"]["beta"], final_phase_change_s=record["final_phase_change_s"],
        history=[dict(position=step["fit"]["parameters"], score=step["fit"]["score"],
                      evaluations=step["fit"].get("evaluations"), phase_change_s=step["phase_change_s"])
                 for step in record["history"]],
    )


def arm_witness(problem, entries, powers, means, record):
    """Capture what actually entered the final likelihood in support/phase units."""
    from leo.analysis.localization_v3.predictive_linear import linear_geometry

    p = problem
    curves, active_families = {}, set()
    for k, (row, member, sl, alias) in enumerate(zip(p.rows, p.members, p.slices, p.alias, strict=True)):
        mask = p.keep[sl]
        track = p.scan.tracks[member]
        label = int(row["candidate_norad"])
        ids = np.asarray(track["observation_ids"])[mask].tolist()
        curves[row["component"]] = dict(norad=label, alias=int(alias), ids=ids)
        if ids:
            active_families.add(label)
            curves[row["component"]].update(
                power=float(powers[k]), clock_cfo_rf=fingerprint(track["times"][mask], track["values"][mask], p.q[sl][mask]),
                sigma=fingerprint(p.point_noise[sl][mask]), hardware=fingerprint(p.hardware[sl][mask]),
                smooth=fingerprint(p.smooth[sl][mask]),
            )

    predictive = {}
    if entries:
        view, values, sigma, _groups, slices = linear_geometry(p, entries)
        for entry, sl in zip(entries, slices, strict=True):
            track = p.scan.tracks[entry["track_index"]]
            label = int(entry["norad"])
            active_families.add(label)
            predictive[entry["component"]] = dict(
                ids=entry["observation_ids"], norad=label, alias=entry["alias"],
                cross_receiver=entry["cross_receiver_curved_support"],
                clock_cfo_rf=fingerprint(track["times"], track["values"], view.q[sl]),
                lifted_variance=fingerprint(values[sl], sigma[sl]),
            )

    families = {}
    for k, label in enumerate(p.labels):
        norad = int(p.scan.norads[label])
        modes = p.mode_bank
        sky = p.sky
        span = slice(3*k, 3*k+3)
        families[str(norad)] = dict(
            active=norad in active_families, orbital_modes=label in p.supported,
            phase_width=float(p.phase_sigma[k]), signed_prior_mean=float(means[k]),
            phase_reference=float(p.reference[k]), posterior_phase=float(record["state"]["phases"][label]),
            causal_sky=fingerprint(sky["position_km"][k], sky["velocity_km_s"][k]),
            mode_geometry=fingerprint(modes["position_km"][span], modes["velocity_km_s"][span]),
        )
    calculated = p.calculate(record["endpoint_east_north_km"])
    return dict(curves=curves, predictive=predictive, families=families, fit=fit_record(record),
                phase_labels=len(p.labels), orbital_mode_families=len(p.supported),
                likelihood_columns=calculated["features"].shape[1], total_curve_slots=len(p.rows),
                original_noise=p.scan.fixed_window_noise_sha256, original_previous_tle=p.scan.previous_tle_sha256,
                timing_origin_ns=p.scan.origin_utc_ns, normalization=float(calculated["normalization_constant"]))


def fit_pair(candidate, means, audit, record):
    from leo.analysis.localization_v3 import event_position

    scan, node, keep, powers, model, entries = (candidate[key] for key in (
        "scan", "node", "keep", "powers", "model", "entries"))
    results, problems = {}, {}
    original = event_position.make_event_problem

    def capture(*values, **options):
        p = original(*values, **options)
        problems[values[3]] = p
        return p

    audit["named_arm_clocks"] = {}
    with patch.object(event_position, "make_event_problem", capture):
        for arm in ARMS:
            started = now()
            try:
                results[arm] = event_position.refit(scan, node, keep, arm, powers, means, model, [], entries)
            finally:
                audit["named_arm_clocks"][arm] = clock(started)
    started = now()
    record.update(model=model, arms={arm: arm_witness(problems[arm], entries, powers, means, results[arm])
                                     for arm in ARMS})
    audit["likelihood_witness_clock"] = clock(started)
    return results


@contextmanager
def binding(witness):
    import lighter_joint_estimator
    from blind_joint_signed import update as signed_update

    previous = lighter_joint_estimator.update
    paid = False

    def update(prepared, ordinary, measured):
        if paid:
            measured["named_survivor_fit"] = {"status": "paired_budget_already_paid"}
            return previous(prepared, ordinary, measured)
        audit = measured["named_survivor_fit"] = {"status": "unqualified"}

        def both(candidate, means):
            nonlocal paid
            paid = True
            audit["status"] = "started"
            return fit_pair(candidate, means, audit, witness)

        status = signed_update(prepared, ordinary, measured, fit_pair=both)
        if paid:
            audit["status"] = "accepted" if status is not ordinary else "original_ordinary_pair"
        return status

    with patch.object(lighter_joint_estimator, "update", update):
        yield
