"""Matched final-stage constrained fits, exact orbit gates and native ownership."""

import hashlib
import json
from copy import deepcopy

import numpy as np
from scipy.optimize import minimize

from leo.analysis.localization_v3.feasible import feasible_fit
from leo.analysis.localization_v3.phase_reference import phase_refresh
from leo.analysis.localization_v3.reassociation_context import ARMS, build, family_score, objective
from leo.analysis.localization_v3.recovery_fragments import original_graph_view
from leo.analysis.localization_v3.recovery_gates import exact_gate_replay, gate_slacks
from leo.analysis.localization_v3.recovery_inventory import memberships


def fit(d, baseline_owners, arm, start, constrained=False, rounds=15):
    reference = d["problems"][arm][0].reference.copy()
    x = np.asarray(start)
    history = []
    for epoch in range(rounds):
        p, dd = build(d, arm, reference)

        def fun(v, p=p, dd=dd):
            return objective(p, dd, v)

        if constrained:
            opt = feasible_fit(
                fun,
                lambda v, p=p, dd=dd: list(gate_slacks(p, v, dd["entries"]).values()),
                x,
                [-12.5] * 2,
                [12.5] * 2,
                iterations=40,
            )
            x = np.asarray(opt["parameters"])
            success = opt["solver_success"]
            message = opt["solver_message"]
            nfev = opt["evaluations"]
        else:
            opt = minimize(
                fun,
                x,
                method="L-BFGS-B",
                bounds=[(-12.5, 12.5)] * 2,
                options=dict(maxiter=35, maxfun=140, eps=0.001, ftol=1e-10, gtol=1e-4, maxls=15),
            )
            x = opt.x
            success = bool(opt.success)
            message = str(opt.message)
            nfev = int(opt.nfev)
        updated, check = phase_refresh(p.state(x)["phases"][p.labels], reference, limit_s=30)
        history.append(dict(x=x, success=success, message=message, nfev=nfev, **check))
        if check["phase_change_s"] <= 0.01:
            break
        if epoch < rounds - 1:
            reference = updated
    c = p.calculate(x)
    slacks = gate_slacks(p, x, dd["entries"])
    bad = {k: v for k, v in slacks.items() if v < 0}
    exact = []
    for j in sorted(
        {r["candidate_index"] for r, sl in zip(p.rows, p.slices, strict=True) if p.keep[sl].any()}
    ):
        p.explicit_phase_family = j
        v = exact_gate_replay(p, x, dd["entries"])
        exact.append(
            dict(
                norad=int(p.scan.norads[j]),
                all_pass=v["all_pass"],
                failed={k: v for k, v in v["all_gate_slacks"].items() if v < 0},
                maximum_difference_hz=v["maximum_linearization_difference_hz"],
            )
        )
    if hasattr(p, "explicit_phase_family"):
        del p.explicit_phase_family
    _, fd = family_score(dd["families"], dd, p, x, details=True)
    mixture_pass = all(g["compatible"] for f in fd for g in f["gates"])
    _, _, _, owners = memberships(original_graph_view(p, len(p.scan.index)), x, dd["entries"])
    for f in dd["families"]:
        for e in f.entries:
            owners.update({o: e["norad"] for o in e["observation_ids"]})
    before = baseline_owners[arm]
    lost = [o for o in before if o not in owners]
    added = [o for o in owners if o not in before]
    changed = [o for o, n in before.items() if o in owners and owners[o] != n]
    allpass = not bad and all(r["all_pass"] for r in exact) and mixture_pass
    params = []
    begin = p.hardware.shape[1] + p.smooth.shape[1]
    for k, j in enumerate(p.labels):
        orb = (
            c["coefficient"][
                begin + len(p.labels) + 3 * p.supported.index(j) : begin
                + len(p.labels)
                + 3 * p.supported.index(j)
                + 3
            ]
            if j in p.supported
            else []
        )
        params.append(
            dict(
                norad=int(p.scan.norads[j]),
                phase_s=float(p.state(x)["phases"][j]),
                phase_sigma_s=float(p.phase_sigma[k]),
                orbital_standardized=orb,
            )
        )
    tracks = []
    for r, i, sl in zip(p.rows, p.members, p.slices, strict=True):
        use = p.keep[sl]
        if not use.any():
            continue
        t = p.scan.tracks[i]
        tracks.append(
            dict(
                component=r["component"],
                norad=r["candidate_norad"],
                receiver=t["receiver"],
                channel=t["channel"],
                times_s=t["times"][use],
                values_hz=p.values[sl][use],
                residual_hz=c["conditional_residual_hz"][sl][use],
                observation_ids=[o for o, u in zip(t["observation_ids"], use, strict=True) if u],
            )
        )
    return dict(
        x=x,
        latlon=d["scan"].search_region.latlon(x),
        error_m=None,
        objective=fun(x),
        rms_hz=float(np.sqrt(np.mean(c["conditional_residual_hz"][p.keep] ** 2))),
        history=history,
        reference=reference,
        phase_closed=check["phase_change_s"] <= 0.01,
        optimizer_success=success,
        all_gates_pass=allpass,
        failed_gates=bad,
        exact=exact,
        mixture_gates_pass=mixture_pass,
        active_points=int(p.keep.sum()),
        lost_ids=lost,
        added_ids=added,
        reassigned_ids=changed,
        proposed_owners=owners,
        parameters=params,
        tracks=tracks,
        qualified=bool(allpass and check["phase_change_s"] <= 0.01 and success and not lost),
        qualification_scope=(
            "RF/phase/optimizer/orbit/ownership screening; "
            "not independent identity validation or complete production acceptance"
        ),
    )


def fit_rows(context, owners, starts, allowed, *, on_row=None, state_sink=None):
    """Same two starts/budgets in both arms, complete failures never hidden.

    The application owns process deadlines and checkpoint persistence. It may
    observe completed rows, but cannot publish a partially evaluated winner.
    """
    rows = []
    base = context["problems"]["fitted_c"][0]
    expected = sorted(
        o
        for i, sl in zip(base.members, base.slices, strict=True)
        for o, use in zip(context["scan"].tracks[i]["observation_ids"], base.keep[sl], strict=True)
        if use
    )
    for arm in ARMS:
        for label, start in starts.items():
            try:
                row = fit(context, owners, arm, start, True, rounds=15)
                p, ctx = build(context, arm, np.asarray(row["reference"]))
                _, details = family_score(
                    ctx["families"], ctx, p, np.asarray(row["x"]), details=True
                )
                row["phase_boundary_masses"] = [f["phase_boundary_mass"] for f in details]
                row["endpoint_latlon"] = list(row["latlon"])
                row["mixture_phase_interior"] = all(
                    f["phase_boundary_mass"] < 0.01 for f in details
                )
                row["qualified"] &= row["mixture_phase_interior"]
                ids = sorted(o for track in row["tracks"] for o in track["observation_ids"])
                if ids != expected or len(ids) != len(set(ids)):
                    raise ValueError("Native evidence changed")
                row["unexpected_reassigned_ids"] = [
                    o for o in row["reassigned_ids"] if owners[arm][o] not in allowed
                ]
                row["qualified"] &= not row["unexpected_reassigned_ids"]
                row["owners_sha256"] = hashlib.sha256(
                    json.dumps(row["proposed_owners"], sort_keys=True).encode()
                ).hexdigest()
                row["native_ids_sha256"] = hashlib.sha256("\n".join(ids).encode()).hexdigest()
                row.update(arm=arm, start=label, status="complete")
                if state_sink is not None and row["qualified"]:
                    # Internal ownership transfer: retain the already rebuilt
                    # endpoint likelihood for presentation, without refitting.
                    state_sink[(arm, label)] = (p, np.asarray(row["x"]).copy())
            except Exception as exc:
                row = dict(
                    arm=arm, start=label, status="incomplete", qualified=False, reason=repr(exc)
                )
            rows.append(row)
            if on_row is not None:
                on_row(deepcopy(row))
    return rows


def paired(rows):
    return {
        arm: min(
            (r for r in rows if r["arm"] == arm and r.get("qualified")),
            key=lambda r: r["objective"],
            default=None,
        )
        for arm in ARMS
    }
