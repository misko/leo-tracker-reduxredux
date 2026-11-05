"""Owned conditional position trials preserving selected family likelihoods."""

import copy

import numpy as np
from scipy.optimize import minimize
from sgp4.api import Satrec

from leo.analysis.localization_v3.gap_fragments import append_branch
from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from leo.analysis.localization_v3.joint_recovery import joint_inputs
from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.orbits import ecef_states
from leo.analysis.localization_v3.phase_reference import phase_refresh
from leo.analysis.localization_v3.recovery_fragments import original_graph_view
from leo.analysis.localization_v3.recovery_gates import exact_gate_replay
from leo.analysis.localization_v3.recovery_inventory import memberships
from leo.analysis.research.continuous_curve_fit import paired_phase_frequency
from leo.analysis.research.orbit_uncertainty import paired_frequency_modes
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.predictive_track import phase_resolution_agreement, receiver_design
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from leo.sky.propagation import ElementSetCatalogue

ARMS = ("c0", "fitted_c")


def family_score(families, d, p, x, details=False, *, optimize_contractions=False):
    if not families:
        return (0.0, []) if details else 0.0
    if len(families) == 1:
        f = families[0]
        v = f.evaluate(p, x, d["powers"], d["entries"], details=details, refine_phase=details)
        return (v["negative_twice_log_density"], [v]) if details else v
    if len(families) != 2:
        raise ValueError("Exact two-family compute cap exceeded")
    joint = two_family_phase_evidence(
        *joint_inputs(families, p, x, d["powers"], d["entries"]),
        optimize_contractions=optimize_contractions,
    )
    if not details:
        return joint["negative_twice_log_density"]
    c = p.curved_calculate(x) if d["entries"] else p.calculate(x)
    coef = c["coefficient"]
    rows = []
    for k, f in enumerate(families):
        phase = float(f.phases[joint["joint_map_indices"][k]])
        orb = np.asarray(joint["orbital_map_mean"][k])
        bank = {key: value[:1] if key != "time_s" else value for key, value in f.bank.items()}
        modes = {key: value[:3] if key != "time_s" else value for key, value in f.modes.items()}
        ff, ee = paired_phase_frequency(
            bank,
            f.times,
            np.zeros(len(f.times), int),
            np.array([phase]),
            *d["scan"].search_region.latlon(x),
        )
        uu = paired_frequency_modes(
            bank,
            modes,
            f.times,
            np.zeros(len(f.times), int),
            np.array([phase]),
            *d["scan"].search_region.latlon(x),
        )
        h = np.concatenate(
            [
                receiver_design(
                    t["times"],
                    t["rf_hz"],
                    t["receiver"],
                    t["channel"],
                    f.scan.rx_basis[e["track_index"]],
                    fitted_c=p.fitted_c,
                )
                for t, e in zip(f.tracks, f.entries, strict=True)
            ]
        )
        pred = h @ coef[: h.shape[1]] + (ff + uu @ orb) * f.q
        raw = f.values - pred
        diagnostics = []
        gates = []
        for e, tr, sl in zip(f.entries, f.tracks, f.slices, strict=True):
            v = profile(
                raw[sl],
                np.zeros(sl.stop - sl.start),
                *f.scan.white[e["track_index"]],
                bias_sigma=300,
            )
            noise = {
                a: b[0].item() for a, b in batch_noise_screen(v["innovations"], tr["times"]).items()
            }
            compatible = bool(
                v["rms"][0] <= 450
                and abs(v["bias"][0]) <= 3000
                and v["alias"][0] == 0
                and noise["noise_screen_pass"]
                and ee[sl].min() >= 0
            )
            gates.append(dict(compatible=compatible, component=e["component"], norad=e["norad"]))
            diagnostics.append(
                dict(
                    times_s=tr["times"],
                    CFO_hz=tr["values"],
                    prediction_CFO_hz=pred[sl] - e["alias"] * PERIOD,
                    raw_residual_hz=raw[sl],
                    profile_RMS_hz=float(v["rms"][0]),
                    profile_bias_hz=float(v["bias"][0]),
                    noise=noise,
                )
            )
        weights = joint["phase_marginals"][k]
        rows.append(
            dict(
                phase_map_s=phase,
                orbital_posterior_mean=orb,
                gates=gates,
                diagnostics=diagnostics,
                phase_boundary_mass=float(weights[abs(f.phases) >= f.phase_limit_s - 0.1].sum()),
                joint_not_factorized=True,
            )
        )
    return joint["negative_twice_log_density"], rows


def add_target(d, source, winner, catalogue, observations, owners):
    # A rejected trial cannot alter the selected scan shared with another trial.
    scan = copy.copy(d["scan"])
    for attr in (
        "causal_uncertainty_modes",
        "previous_shape_cache",
        "reference_motion_derivatives",
        "mean_motion_derivatives",
        "element_derivatives",
        "reference",
    ):
        if hasattr(scan, attr):
            setattr(scan, attr, dict(getattr(scan, attr)))
    d["scan"] = scan
    n = winner["norad"]
    record = catalogue["elements"][str(n)]
    existing = np.flatnonzero(scan.norads == n)
    if len(existing):
        j = int(existing[0])
    else:
        j = len(scan.norads)
        cat = ElementSetCatalogue((str(n),), (n,), (Satrec.twoline2rv(*record["lines"]),))
        pos, vel, good = ecef_states(cat, scan.origin_utc_ns, scan.sky["time_s"])
        if not good.all():
            raise ValueError("Candidate propagation failure")
        scan.norads = np.r_[scan.norads, n]
        scan.sky = dict(
            scan.sky,
            position_km=np.concatenate([scan.sky["position_km"], pos]),
            velocity_km_s=np.concatenate([scan.sky["velocity_km_s"], vel]),
            phase_sigma_s=np.r_[scan.sky["phase_sigma_s"], 1.0],
        )
        scan.elements = dict(
            scan.elements,
            **{
                str(n): dict(
                    lines=record["lines"],
                    provenance={k: v for k, v in record.items() if k != "lines"},
                )
            },
        )
    track = scan.tracks[source["track_index"]]
    ix = np.asarray(source["source_local_indices"])
    ids = source["observation_ids"]
    if list(track["observation_ids"]) == ids:
        i = source["track_index"]
    else:
        lookup = {o["observation_id"]: o for o in observations}
        y = track["values"][ix]
        lifts = np.rint(
            (y - np.array([lookup[o]["measured_cfo_hz"] for o in ids])) / PERIOD
        ).astype(int)
        branch = dict(
            branch_id=source["fragment_id"],
            observation_ids=ids,
            times_s=track["times"][ix],
            values_hz=y,
            alias_lifts=lifts,
            receiver=track["receiver"],
            channel=track["channel"],
            rf_hz=track["rf_hz"],
            quality_status="unchanged_gap_fragment",
            pieces=track["pieces"],
            RMS_hz=track["residual_rms_hz"],
        )
        scan, i = append_branch(
            scan, branch, observations, set(owners["c0"]) | set(owners["fitted_c"])
        )
        d["scan"] = scan
    entry = dict(
        track_index=i,
        component=scan.tracks[i]["key"],
        candidate_index=j,
        norad=n,
        alias=winner["alias"],
        points=len(ids),
        observation_ids=ids,
    )
    return entry


def prediction_scan(scan, bound):
    """Extend propagation only in a private predictive view, never calibration."""
    if bound <= 15:
        return scan
    view = copy.copy(scan)
    grid = np.arange(min(-40.0, min(scan.sky["time_s"])), max(341.0, max(scan.sky["time_s"]) + 1))
    numbers = tuple(map(int, scan.norads))
    cat = ElementSetCatalogue(
        tuple(map(str, numbers)),
        numbers,
        tuple(Satrec.twoline2rv(*scan.elements[str(n)]["lines"]) for n in numbers),
    )
    p, v, good = ecef_states(cat, scan.origin_utc_ns, grid)
    if not good.all():
        raise ValueError("Expanded private orbit propagation failure")
    view.sky = dict(scan.sky, time_s=grid, position_km=p, velocity_km_s=v)
    for attr in (
        "causal_uncertainty_modes",
        "previous_shape_cache",
        "reference_motion_derivatives",
        "mean_motion_derivatives",
    ):
        if hasattr(view, attr):
            setattr(view, attr, {})
    return view


def fit_pair(owners_before, d, extra, *, deadline, clock, on_arm=None):
    pair = {}
    allfamilies = d["families"] + ([extra] if extra else [])
    for arm in ARMS:
        oldp, x = d["problems"][arm]
        x = x.copy()
        reference = oldp.reference.copy()
        history = []
        for epoch in range(3):
            p = d["factory"](arm, reference)

            def objective(v, p=p):
                if clock() > deadline:
                    raise TimeoutError("Bounded conditional position trial exhausted")
                c = p.calculate(v)
                return (
                    c["negative_twice_elbo"]
                    + np.sum(np.minimum(0, c["elevation"][p.keep]) ** 2) / 4
                    + family_score(allfamilies, d, p, v)
                )

            opt = minimize(
                objective,
                x,
                method="L-BFGS-B",
                bounds=[(-12.5, 12.5)] * 2,
                options=dict(maxiter=30, maxfun=100, eps=0.001, ftol=1e-10, gtol=1e-4, maxls=15),
            )
            x = opt.x
            phase, check = phase_refresh(p.state(x)["phases"][p.labels], reference, limit_s=30)
            history.append(
                dict(
                    success=bool(opt.success), message=str(opt.message), nfev=int(opt.nfev), **check
                )
            )
            if check["phase_change_s"] <= 0.01:
                break
            if epoch < 2:
                reference = phase
        score, details = family_score(allfamilies, d, p, x, details=True)
        _, _, ids, owners = memberships(original_graph_view(p, len(p.scan.index)), x, d["entries"])
        for f in d["families"]:
            for e in f.entries:
                owners.update({o: e["norad"] for o in e["observation_ids"]})
        changed = [o for o, n in owners_before[arm].items() if owners.get(o) != n]
        labels = {
            r["candidate_index"] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()
        } | {e["candidate_index"] for e in d["entries"]}
        exact = []
        for j in sorted(labels):
            p.explicit_phase_family = j
            exact.append(dict(norad=int(p.scan.norads[j]), **exact_gate_replay(p, x, d["entries"])))
        if hasattr(p, "explicit_phase_family"):
            del p.explicit_phase_family
        # Refine only the newly integrated family; incumbent quadrature is the
        # same sealed numerical model in control and candidate. Joint evidence
        # retains its shared receiver covariance in every refinement.
        quad = dict(local_agreement=True, reason="control has no new quadrature")
        if extra:
            step = extra.receipt["phase_step_s"]
            finer = [extra] + [
                NewFamily(
                    extra.scan,
                    extra.entries,
                    d["model"],
                    phase_step=h,
                    phase_limit_s=extra.phase_limit_s,
                    allow_uncalibrated_label=True,
                )
                for h in (step / 2, step / 4)
            ]
            offsets = np.array([[0, 0], [0.025, 0], [-0.025, 0], [0, 0.025], [0, -0.025]])
            scores = np.array(
                [[family_score(d["families"] + [f], d, p, x + v) for f in finer] for v in offsets]
            )
            quad = dict(
                steps_s=[step, step / 2, step / 4],
                scores=scores,
                **phase_resolution_agreement(scores),
            )
        checks = dict(
            optimizer=bool(opt.success),
            phase=history[-1]["phase_change_s"] <= 0.01,
            incumbent_exact_orbits=all(r["all_pass"] for r in exact),
            existing_owners_preserved=not changed,
            family_residuals=all(g["compatible"] for f in details for g in f["gates"]),
            phase_interior=all(f["phase_boundary_mass"] < 0.01 for f in details),
            quadrature=quad["local_agreement"],
        )
        row = dict(
            endpoint_east_north_km=x,
            endpoint_latlon=d["scan"].search_region.latlon(x),
            negative_twice_elbo=float(p.calculate(x)["negative_twice_elbo"] + score),
            history=history,
            checks=checks,
            all_checked_gates_pass=all(checks.values()),
            family_details=details,
            quadrature=quad,
            changed_incumbent_ids=changed,
            incumbent_exact_orbits=exact,
            baseline_associated=len(owners_before[arm]),
            proposed_added_points=extra.entries[0]["points"] if extra else 0,
            phase_reference=p.reference,
        )
        pair[arm] = row
        if on_arm is not None:
            on_arm(arm, copy.deepcopy(row))
    return pair
