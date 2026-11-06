def fit_shared(context, inventory, annotations, *, conditional_satellite_refresh=False,
               map_arms=None):
    d, targets, receipts, fragments, count = _targets(context, inventory, annotations, shared=True)
    protocol = dict(
        targets=targets,
        annotation_receipts=receipts,
        matched_c_arms=True,
        phase_rounds=5,
        steps=48,
        start=[0, 0],
        position_fit="regional_unconstrained",
        box_width_km=25,
        target_calibrates_receiver=False,
        target_updates_unobserved_satellite_parameters=False,
        original_noise_weights_and_priors=True,
        original_noise_weights=True,
        noise_policy="original",
        orphan_phase_refresh=False,
        orphan_orbit_prior=False,
        GPS_used=False,
        future_TLE=False,
        target_orbit_prior=False,
        shared_satellite_refresh=False,
        conditional_satellite_refresh=conditional_satellite_refresh,
        inactive_graph_member_as_predictive=True,
        inactive_fragment_sources=fragments,
        graph_bundle_sources=[],
        excluded_predictive_parameter_uncertainty_conditioned_away=conditional_satellite_refresh,
        native_branches=None,
        native_sources=[],
        original_graph_count=count,
    )
    native = any("gap_source" in a for a in annotations)
    if native:
        protocol["inactive_graph_member_as_predictive"] = False
        protocol["native_sources"] = [
            a["protocol"]["target"]["gap_source_sha256"] for a in annotations
        ]
    result = dict(protocol=protocol)
    variants = [("control", [])] + [(f"target_{k}", [t]) for k, t in enumerate(targets)]
    if len(targets) > 1:
        variants.append(("combined", targets))
    for name, extras in variants:
        entries = d["entries"] + extras

        def fit_arm(arm, entries=entries, extras=extras):
            x, reference, history = np.zeros(2), np.zeros(len(d["means"])), []
            for _ in range(5):
                p = _problem(
                    d,
                    arm,
                    reference,
                    entries,
                    conditional_families=(
                        [t["candidate_index"] for t in targets]
                        if conditional_satellite_refresh
                        else None
                    ),
                )
                fitted = fit(p, x, iterations=48)
                x = np.asarray(fitted["parameters"])
                reference, check = numerics.refresh(d, p, p.state(x)["phases"][p.labels], reference)
                history.append(dict(endpoint_east_north_km=x, fit=fitted, **check))
            row = summary(p, x, entries)
            _, _, ids, owners = memberships(original_graph_view(p, count), x, entries)
            old = set(inventory["policy"][arm]["proposed_associated_ids"])
            receiver_change = p.calculate(x).get(
                "shared_satellite_receiver_change", row["linear_calibration_max_difference"]
            )
            if receiver_change > 1e-10:
                raise ValueError("predictive data changed receiver calibration at fixed position")
            row.update(
                history=history,
                final_phase_change_s=check["phase_change_s"],
                proposed_associated_ids=sorted(ids),
                proposed_owners=owners,
                added_points=len(ids - old),
                lost_points=len(old - ids),
                targets=[
                    g
                    for g in row["linear_gates"]
                    if g["component"] in {e["component"] for e in extras}
                ],
            )
            if extras:
                calc, diagnostics = p.calculate(x), []
                for entry, sl in zip(p.linear_entries, p.linear_slices, strict=True):
                    if entry not in extras:
                        continue
                    t = p.scan.tracks[entry["track_index"]]
                    raw = calc["linear_raw_prediction_residual_hz"][sl]
                    terms = profile(
                        raw,
                        np.zeros(len(raw)),
                        *p.scan.white[entry["track_index"]],
                        bias_sigma=300.0,
                    )
                    diagnostics.append(
                        dict(
                            component=entry["component"],
                            norad=entry["norad"],
                            times_s=t["times"],
                            CFO_hz=t["values"],
                            predicted_CFO_hz=t["values"] - raw,
                            residual_hz=terms["residual"][0],
                            RMS_hz=float(terms["rms"][0]),
                            bias_hz=float(terms["bias"][0]),
                        )
                    )
                row["target_diagnostics"] = diagnostics
                if native:
                    row["native_target_diagnostics"] = diagnostics
            if conditional_satellite_refresh:
                row["shared_satellite_replay"] = exact_shared_replay(p, x, entries)
            return row

        # Numerical replay maintains ordered mutable receipts in the parent.
        mapper = map if d.get("numerical_policy") is not None else (map_arms or map)
        pair = dict(zip(ARMS, mapper(fit_arm, ARMS), strict=True))
        valid = pair_passes(pair, include_linear=True) and all(
            r["lost_points"] == 0 and r["final_phase_change_s"] <= 0.01 for r in pair.values()
        )
        if conditional_satellite_refresh:
            valid = valid and all(
                r["shared_satellite_replay"]["phases_in_bounds"]
                and r["shared_satellite_replay"]["maximum_phase_linearization_error_hz"] <= 1
                for r in pair.values()
            )
        result[name] = dict(
            arms=pair,
            baseline=inventory["policy"],
            paired_valid=valid,
            target_entries=extras,
            original_calibration_mask=d["keep"],
            target_calibrates_receiver=False,
            target_updates_unobserved_satellite_parameters=False,
            orphan_phase_refresh=False,
            orphan_orbit_prior=False,
            noise_policy="original",
            position_fit="regional_unconstrained",
            target_orbit_prior=False,
            shared_satellite_refresh=False,
            conditional_satellite_refresh=conditional_satellite_refresh,
            no_production_change=True,
        )
    return result
