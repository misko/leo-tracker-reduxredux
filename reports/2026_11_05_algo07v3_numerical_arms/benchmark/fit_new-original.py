def fit_new(context, inventory, annotations, *, optimizer="lbfgsb", map_arms=None):
    if optimizer not in ("lbfgsb", "powell"):
        raise ValueError("unknown matched position optimizer")
    d, targets, _, fragments, count = _targets(context, inventory, annotations, shared=False)
    family = NewFamily(
        d["scan"], targets, d["model"], phase_step=0.025, allow_uncalibrated_label=True
    )
    protocol = dict(
        targets=targets,
        validation=[a["result"]["track_id"] for a in annotations],
        family_prior=family.receipt,
        inactive_fragment_sources=fragments,
        measurement_refinements=[],
        graph_bundle_sources=[],
        original_graph_count=count,
        optimizer=optimizer + " normalized joint objective",
        maxiter=48,
        maxfun=240,
        phase_rounds=5,
        start=[0, 0],
        box_width_km=25,
        control_uses_same_optimizer=True,
        c0_vs_fitted_c=True,
        GPS_used=False,
        future_TLE=False,
        phase_step_s=0.025,
        uncalibrated_label=True,
        phase_resolution_audit=True,
        postfit_audit_evaluations_per_arm=15,
    )
    result = dict(protocol=protocol)
    for variant, include in [("control", False), ("new_family", True)]:
        def fit_arm(arm, include=include):
            x, reference, history = np.zeros(2), np.zeros(len(d["means"])), []
            for _ in range(5):
                p = _problem(d, arm, reference, d["entries"])

                def objective(z, p=p, include=include):
                    c = p.calculate(z)
                    penalty = float(np.sum(np.minimum(0, c["elevation"][p.keep]) ** 2) / 4)
                    return (
                        c["negative_twice_elbo"]
                        + penalty
                        + (family.evaluate(p, z, d["powers"], d["entries"]) if include else 0.0)
                    )

                if optimizer == "lbfgsb":
                    opt = numerics.minimize(
                        d,
                        minimize,
                        objective,
                        x,
                        method="L-BFGS-B",
                        bounds=[(-12.5, 12.5)] * 2,
                        options=dict(
                            maxiter=48, maxfun=240, eps=0.001, ftol=1e-10, gtol=1e-4, maxls=20
                        ),
                    )
                else:
                    opt = numerics.minimize(
                        d,
                        minimize,
                        objective,
                        x,
                        method="Powell",
                        bounds=[(-12.5, 12.5)] * 2,
                        options=dict(maxiter=48, maxfev=240, ftol=1e-10, xtol=1e-5),
                    )
                x = np.asarray(opt.x)
                reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
                history.append(
                    dict(
                        endpoint_east_north_km=x,
                        objective=float(opt.fun),
                        success=bool(opt.success),
                        message=str(opt.message),
                        nfev=opt.nfev,
                        **check,
                    )
                )
            row = summary(p, x, d["entries"])
            _, _, ids, _ = memberships(original_graph_view(p, count), x, d["entries"])
            old = set(inventory["policy"][arm]["proposed_associated_ids"])
            if include:
                detail = family.evaluate(p, x, d["powers"], d["entries"], details=True)
                row["family"] = detail
                row["incumbent_objective"] = row["negative_twice_elbo"]
                row["negative_twice_elbo"] += detail["negative_twice_log_density"]
                row["linear_gates"] += detail["gates"]
                ids.update(o for e in targets for o in e["observation_ids"])
                row["phase_resolution_audit"] = resolution_audit(
                    family, p, x, d["powers"], d["entries"], d["model"]
                )
            row.update(
                history=history,
                final_phase_change_s=check["phase_change_s"],
                proposed_associated_ids=sorted(ids),
                added_points=len(ids - old),
                lost_points=len(old - ids),
            )
            return row

        mapper = map if d.get("numerical_policy") is not None else (map_arms or map)
        pair = dict(zip(ARMS, mapper(fit_arm, ARMS), strict=True))
        valid = pair_passes(pair, include_linear=True) and all(
            v["lost_points"] == 0
            and v["history"][-1]["success"]
            and v["final_phase_change_s"] <= 0.01
            for v in pair.values()
        )
        if include:
            valid = valid and all(
                v["family"]["phase_boundary_mass"] < 0.01
                and v["phase_resolution_audit"]["local_agreement"]
                for v in pair.values()
            )
        result[variant] = dict(
            arms=pair,
            baseline=inventory["policy"],
            paired_valid=valid,
            target_entries=targets if include else [],
            no_production_change=True,
            receiver_calibration_from_target=False,
            shared_predictive_uncertainty=True,
            phase_resolution_checked=bool(include),
        )
    return result
