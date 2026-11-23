"""Transplant only signed phase references and dimensionless curved precisions."""

from collections import Counter
from time import process_time_ns

import numpy as np

from centre_oracle_iterative import Profile, trust_fit
from centre_oracle_step import CENTRE, exact_readout


CELLS = ("causal_unit", "phase_only", "weights_only", "phase_and_weights")


def effective_precision(powers, tau, kept):
    powers, tau, kept = np.asarray(powers), np.asarray(tau), np.asarray(kept, dtype=int)
    if (powers.ndim != 1 or tau.shape != powers.shape or not np.isfinite(powers).all()
            or not np.isfinite(tau).all() or np.any(powers <= 0) or np.any(powers > 1)
            or np.any(tau[kept] <= 0) or np.any(np.delete(tau, np.unique(kept)) != 0.)):
        raise ValueError("Expected positive kept group precision and zero inactive precision")
    return powers * tau


def layout(problem, entries):
    from leo.analysis.localization_v3.predictive_linear import linear_geometry
    from leo.analysis.research.retained_track_likelihood import PERIOD

    p = problem
    result = []
    for group, (track, row, sl, alias) in enumerate(zip(
        p.members, p.rows, p.slices, p.alias, strict=True,
    )):
        member = p.scan.tracks[track]
        if (member["key"] != row["component"] or not np.all(p.noise_groups[sl] == group)
                or not np.array_equal(p.values[sl], member["values"] + alias * PERIOD)):
            raise ValueError("Curved group or absolute signed measurement changed")
        result.append(dict(
            component=member["key"], norad=int(row["candidate_norad"]), alias=int(alias),
            ids=[oid for oid, keep in zip(member["observation_ids"], p.keep[sl], strict=True) if keep],
            noise_hz=p.point_noise[sl][p.keep[sl]].tolist(),
        ))
    _, values, noise, groups, slices = linear_geometry(p, entries)
    for group, (entry, sl) in enumerate(zip(entries, slices, strict=True)):
        track = p.scan.tracks[entry["track_index"]]
        if (track["key"] != entry["component"] or not np.all(groups[sl] == group)
                or list(track["observation_ids"]) != list(entry["observation_ids"])
                or int(p.scan.norads[entry["candidate_index"]]) != entry["norad"]
                or not np.array_equal(values[sl], track["values"] + entry["alias"] * PERIOD)):
            raise ValueError("Predictive role or absolute signed measurement changed")
        result.append(dict(component=track["key"], norad=entry["norad"], alias=entry["alias"],
                           ids=entry["observation_ids"], noise_hz=noise[sl].tolist()))
    return result


def factor_arm(scan, node, keep, entries, means, model, arm, *, record, original_powers):
    from leo.analysis.localization_v3.event_position import attach_event_predictive, make_event_problem

    begin = process_time_ns()
    reference = np.array(record["phase_reference"])
    donor = make_event_problem(scan, node, keep, arm, reference, original_powers, means, model, [])
    attach_event_predictive(donor, entries, original_powers)
    emitted = donor.calculate(record["endpoint_east_north_km"])
    checked = exact_readout(emitted, keep)
    delta_elbo = float(emitted["negative_twice_elbo"] - record["negative_twice_elbo"])
    if (not np.isfinite(delta_elbo) or abs(delta_elbo) > 1e-5
            or abs(checked["curved_rms_hz"] - record["RMS_hz"]) > 1e-8
            or not 0 <= emitted["final_log_precision_change"] < 1e-5):
        raise ValueError("The provider's released selected objective or converged precisions disagree")
    normalized = np.array(emitted["noise_precision"])
    precision = effective_precision(original_powers, normalized, donor.noise_groups[keep])
    weights = dict(
        groups=[dict(component=source["component"], norad=source["candidate_norad"],
                     rows=int(np.count_nonzero(keep[sl])), family_power=float(power),
                     gamma_precision=float(tau), effective_precision=float(value))
                for source, sl, power, tau, value in zip(
                    donor.rows, donor.slices, original_powers, normalized, precision, strict=True)],
        phase_s=dict(zip((int(scan.norads[j]) for j in donor.labels), reference, strict=True)),
        precision_iterations=int(emitted["precision_iterations"]),
        final_log_precision_change=float(emitted["final_log_precision_change"]),
        signed_replay_delta_elbo=delta_elbo,
    )
    original_layout = layout(donor, entries)
    provider_ns = process_time_ns() - begin

    audits = {}
    cells = {}
    nominal = np.ones(len(node["seed"]["rows"]))
    for name, use_phase, use_weights in zip(CELLS, (False, True, False, True),
                                          (False, False, True, True), strict=True):
        begin = process_time_ns()
        proxy = make_event_problem(scan, node, keep, arm, reference if use_phase else means,
                                   nominal, means, model, [])
        if (layout(proxy, entries) != original_layout or proxy.labels != donor.labels
                or not np.array_equal(proxy.phase_sigma, donor.phase_sigma)):
            raise ValueError("The transplant changed row, group or phase-label correspondence")
        profile = Profile(proxy, entries, means)
        if use_weights:
            profile.noise[:np.count_nonzero(keep)] /= np.sqrt(precision[proxy.noise_groups[keep]])
        fit = trust_fit(profile, proxy.lower, proxy.upper)
        point = fit["history"][-1]["point"]
        cost_ns = process_time_ns() - begin
        begin = process_time_ns()
        for xy in (CENTRE, point):
            if tuple(xy) not in audits:
                audits[tuple(xy)] = exact_readout(donor.calculate(xy), keep)
        fit.update(
            groups=dict(Counter(e["role"] for e in fit["evaluations"])),
            final=dict(point_km=point, latlon=scan.search_region.latlon(point),
                       authoritative=audits[tuple(point)]),
            centre_authoritative=audits[tuple(CENTRE)],
            profile_cpu_ns=cost_ns,
            audit_cpu_ns=process_time_ns()-begin,
        )
        cells[name] = fit
    return dict(provider=weights, provider_cpu_ns=provider_ns, cells=cells,
                checks=dict(curved_groups=len(donor.rows), predictive_groups=len(entries),
                            original_layout_equal=True))
