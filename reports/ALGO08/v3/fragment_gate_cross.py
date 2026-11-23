"""Fixed-position contrasts for an original conditional or predictive fragment."""

from collections import Counter
from itertools import product

import numpy as np


def sections(problem):
    return {problem.scan.tracks[i]["key"]: (k, row, i, sl, int(alias))
            for k, (row, i, sl, alias) in enumerate(zip(
                problem.rows, problem.members, problem.slices, problem.alias, strict=True))}


def transport_phase(recipient, original, donor):
    have = {int(norad): float(phase) for norad, phase in zip(donor["norads"], donor["phase"], strict=True)}
    phase = np.asarray(original, float).copy()
    transferred = 0
    for k, norad in enumerate(recipient):
        if norad in have:
            phase[k] = have[norad]
            transferred += 1
    return phase, transferred


def weighting(problem, powers):
    """Match common *active*, same-signed-alias likelihood groups by fragment and points."""
    result = {}
    for component, (k, row, i, sl, alias) in sections(problem).items():
        track = problem.scan.tracks[i]
        mask = problem.keep[sl]
        if mask.any():
            result[(component, int(row["candidate_norad"]), alias)] = (
                float(powers[k]),
                dict(zip(np.asarray(track["observation_ids"])[mask], problem.point_noise[sl][mask], strict=True)),
            )
    return result


def install_weights(problem, own, donor):
    """Replace donor power on matched active rows and noise on matching IDs only."""
    power = own.copy()
    noise = problem.point_noise.copy()
    coverage = Counter()
    for key, (k, row, i, sl, alias) in sections(problem).items():
        mask = problem.keep[sl]
        if not mask.any():
            continue
        coverage["active_rows"] += 1
        coverage["active_points"] += int(mask.sum())
        donor_row = donor.get((key, int(row["candidate_norad"]), alias))
        if donor_row is None:
            continue
        power[k], by_id = donor_row
        coverage["donor_power_rows"] += 1
        for index, oid in enumerate(problem.scan.tracks[i]["observation_ids"]):
            if mask[index] and oid in by_id:
                noise[sl.start + index] = by_id[oid]
                coverage["donor_noise_points"] += 1
    return power, noise, dict(coverage)


def state(problem, point, components):
    result = problem.calculate(point)
    fitted = problem.state(point)
    frequency, elevation = problem.conditional_frequency(point)
    data = {}
    for name, (k, row, i, sl, alias) in sections(problem).items():
        if name not in components:
            continue
        scan = problem.scan
        track = scan.tracks[i]
        q = track["rf_hz"] / 11.5e9
        hardware = scan.hardware(track, fitted["beta"])
        smooth = q * scan.rx_basis[i] @ fitted["smooth"][track["receiver"] - 1]
        cohort = np.asarray(track["observation_ids"])
        native = np.asarray(track["values"])
        residual = result["conditional_residual_hz"][sl]
        orbit = q * frequency[sl]
        local_constant = problem.values[sl] - orbit - hardware - smooth - residual
        if np.ptp(local_constant) > 1e-6:
            raise ValueError("The original conditional residual could not be separated into curve and fitted terms")
        data[name] = dict(norad=int(row["candidate_norad"]), alias=alias, ids=cohort,
                          times=np.asarray(track["times"]), raw_hz=native, orbit_hz=orbit,
                          hardware_hz=hardware, smooth_hz=smooth, constant_hz=float(local_constant.mean()),
                          elevation=elevation[sl], residual_hz=residual, mask=problem.keep[sl].copy(),
                          point_noise_hz=problem.point_noise[sl], effective_precision=float(result["noise_precision"][k]),
                          phase_s=float(fitted["phases"][row["candidate_index"]]),
                          fitted_c_hz_ghz=float(fitted["beta"][-1]) if problem.fitted_c else 0.0)
    return data


def scope(fragment, point_ids):
    order = {oid: k for k, oid in enumerate(fragment["ids"])}
    if len(order) != len(fragment["ids"]) or len(set(point_ids)) != len(point_ids):
        raise ValueError("Unique matched graph observations are required")
    index = np.asarray([order[oid] for oid in point_ids], dtype=int)
    if len(index) < 4 or np.any(np.diff(index) <= 0):
        raise ValueError("A crossed gate must use the original chronological observation order")
    return index


def peak_step(residual):
    """The original maximum standardized split and its chronologically first maximizing index."""
    n = len(residual)
    splits = np.arange(4, n - 3)
    if not len(splits):
        return None, 0.
    sigma = max(np.std(residual, ddof=1), 75.)
    before = np.cumsum(residual)[splits - 1]
    jump = before / splits - (residual.sum() - before) / (n - splits)
    scores = np.abs(jump) / (sigma * np.sqrt(1 / splits + 1 / (n - splits)))
    j = int(np.argmax(scores))
    return int(splits[j]), float(scores[j])


def local_gate(fragment, point_ids):
    from leo.analysis.localization_v3.acceptance import conditional_gate
    from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
    from leo.analysis.research.retained_track_likelihood import profile, whitening

    ix = scope(fragment, point_ids)
    times = fragment["times"][ix]
    observed = fragment["raw_hz"][ix] - fragment["hardware_hz"][ix] - fragment["smooth_hz"][ix]
    terms = profile(observed, fragment["orbit_hz"][ix], *whitening(times))
    noise = batch_noise_screen(terms["innovations"], times)
    residual = fragment["residual_hz"][ix]
    conditional = conditional_gate(residual, times)
    split, max_step = peak_step(residual)
    if abs(max_step - conditional["diagnostics"]["maximum_step_z"]) > 1e-10:
        raise ValueError("Split witness did not reproduce the original gate diagnostic")
    rms, bias, alias = float(terms["rms"][0]), float(terms["bias"][0]), int(terms["alias"][0])
    minimum = float(np.min(fragment["elevation"][ix]))
    alias_changed = alias != fragment["alias"]
    passing = (rms <= 450 and abs(bias) <= 3000 and noise["noise_screen_pass"][0]
               and conditional["compatible"] and not alias_changed and minimum >= 0)
    return dict(points=len(ix), compatible=bool(passing), conditional_residual_gate=conditional,
                profile_rms_hz=rms, profile_bias_hz=bias, aliases_changed=int(alias_changed), profile_alias=alias,
                profile_diagnostics={key: value[0] for key, value in noise.items()}, minimum_elevation_deg=minimum,
                step_after_id=None if split is None else point_ids[split-1],
                step_before_id=None if split is None else point_ids[split])


def state_terms(left, right, point_ids):
    """Separate orbit from receiver state with no likelihood re-solve."""
    from leo.analysis.localization_v3.acceptance import conditional_gate
    from leo.analysis.research.retained_track_likelihood import PERIOD

    indices = [scope(fragment, point_ids) for fragment in (left, right)]
    own, other = indices
    for key in ("times", "raw_hz"):
        if not np.array_equal(left[key][own], right[key][other]):
            raise ValueError("Crossed gate must retain the same RF observations and clocks")
    if left["norad"] != right["norad"]:
        raise ValueError("Cannot attribute a conditional gate across different target identities")
    shifts = {}
    for key in ("orbit_hz", "hardware_hz", "smooth_hz"):
        shifts[key] = left[key][own] - right[key][other]
    shifts["constant_hz"] = left["constant_hz"] - right["constant_hz"]
    shifts["signed_alias_hz"] = (right["alias"] - left["alias"]) * PERIOD
    residual = left["residual_hz"][own]
    if not np.allclose(residual + sum(shifts.values()), right["residual_hz"][other], rtol=0, atol=1e-7):
        raise ValueError("The independent orbit and receiver terms did not reconstruct the donor residual")
    return {key: dict(rms_hz=float(np.sqrt(np.mean(delta*delta))), mean_hz=float(np.mean(delta)),
                      centered_rms_hz=float(np.std(delta)), gate=conditional_gate(residual + delta, left["times"][own]))
            for key, delta in shifts.items()}


def mask_influence(fragment, full):
    """Compute the single-deletion gate-only sensitivity without refitting."""
    from leo.analysis.localization_v3.acceptance import conditional_gate

    ix = scope(fragment, full)
    times, residual = fragment["times"][ix], fragment["residual_hz"][ix]
    answers = []
    for k, oid in enumerate(full):
        keep = np.arange(len(ix)) != k
        witness = conditional_gate(residual[keep], times[keep])
        answers.append(dict(removed=oid, removal_index=k, time_s=float(times[k]), residual_hz=float(residual[k]),
                            step_z=float(witness["diagnostics"]["maximum_step_z"]), passed=witness["compatible"]))
    return sorted(answers, key=lambda value: (value["step_z"], value["removal_index"]))


def model_problem(frame, arm, anchor, donor=None):
    from leo.analysis.localization_v3 import event_position

    problems = frame["problems"]
    original = problems.get(arm, problems["c0"])
    point = np.asarray(anchor["point"])
    norads = [int(original.scan.norads[label]) for label in original.labels]
    phase, overlap = transport_phase(norads, original.reference, anchor)
    powers, noise, coverage = frame["powers"], None, {}
    if donor is not None:
        powers, noise, coverage = install_weights(original, powers, donor)
    scan, node, keep, means, model, entries = (frame[key] for key in (
        "scan", "node", "keep", "means", "model", "entries"))
    p = event_position.make_event_problem(scan, node, keep, arm, phase, powers, means, model, [])
    if list(p.labels) != list(original.labels):
        raise ValueError("Crossed build changed the recipient phase family layout")
    if noise is not None:
        p.point_noise = noise
    event_position.attach_event_predictive(p, entries, powers)
    event_position.cached(p)
    return p, point, dict(phase_donor_labels=overlap, phase_recipient_labels=len(norads), **coverage)


def factorial(frames, anchors, arm, component, matched):
    """Run the two levels of reconstructed roster, trajectory and original noise/weight source."""
    rows = []
    for roster, trajectory, weights in product(frames, anchors, frames):
        frame = frames[roster]
        donor_frame = frames[weights]
        donor_problem = donor_frame["problems"].get(arm, donor_frame["problems"]["c0"])
        donor = weighting(donor_problem, donor_frame["powers"]) if weights != roster else None
        p, point, coverage = model_problem(frame, arm, anchors[trajectory], donor)
        fragment = state(p, point, {component})[component]
        rows.append(dict(roster=roster, trajectory=trajectory, weights_noise=weights, point=point,
                         gate=local_gate(fragment, matched), source=fitted_fragment(fragment, matched),
                         phase_and_weight_coverage=coverage))
    return rows


def fitted_fragment(fragment, matched):
    ix = scope(fragment, matched)
    return {key: value for key, value in fragment.items()
            if key in ("norad", "alias", "phase_s", "constant_hz", "effective_precision", "fitted_c_hz_ghz")} | {
                "min_point_noise_hz": float(fragment["point_noise_hz"][ix].min()),
                "max_point_noise_hz": float(fragment["point_noise_hz"][ix].max()),
            }
