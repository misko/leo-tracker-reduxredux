def screen_candidates(packet, catalogue, search_region, *, policy="72h_30s", on_target=None):
    """Nominate from each training partition independently under the frozen policy.

    The default is the deployed 72-hour / 30-second policy without a recency
    penalty. This is a candidate screen; shared orbital likelihood fits and
    independent position acceptance still have to follow.
    """
    if policy not in POLICIES:
        raise ValueError("Unknown residual recovery policy")
    policy_table = {policy: POLICIES[policy]}
    records = catalogue["elements"]
    meta = packet["scan_receipt"]
    if catalogue["cutoff_utc_ns"] != meta["cutoff_utc_ns"]:
        raise ValueError("Causal catalogue cutoff does not match the scan")
    nums = np.array(sorted(map(int, records)))
    age = np.array(
        [(meta["cutoff_utc_ns"] - records[str(n)]["element_epoch_utc_ns"]) / 3.6e12 for n in nums]
    )
    collection = np.array(
        [(meta["cutoff_utc_ns"] - records[str(n)]["collected_utc_ns"]) / 3.6e12 for n in nums]
    )
    if not ((age >= 0) & (age <= 72) & (collection >= 0) & (collection <= 72)).all():
        raise ValueError("Causal catalogue violation")
    epoch = age.copy()
    age = np.maximum(age, collection)
    grid = np.arange(-40.0, 341.0)
    cat = ElementSetCatalogue(
        tuple(map(str, nums)),
        tuple(map(int, nums)),
        tuple(Satrec.twoline2rv(*records[str(n)]["lines"]) for n in nums),
    )
    pos, vel, good = ecef_states(cat, meta["origin_utc_ns"], grid)
    failures = nums[~good].tolist()
    nums = nums[good]
    age = age[good]
    epoch = epoch[good]
    collection = collection[good]
    bank = dict(time_s=grid, position_km=pos[good], velocity_km_s=vel[good])
    outputs = []
    phases = np.sort(np.unique(np.r_[np.arange(-30, 31, 2), -15, 15]))
    for target in packet["targets"]:
        source = target["source"]
        t = np.asarray(target["times_s"])
        q = source["rf_hz"] / 11.5e9
        folds = [("full", np.ones(len(t), bool), np.zeros(len(t), bool))]
        for seed in SEEDS:
            train, held, groups = split(t, seed)
            if train.sum() >= 8 and held.sum() >= 4:
                folds.append((str(seed), train, held))
        # Coarse nomination is repeated on training points separately. The
        # target's full-data winner is never injected into a training shortlist.
        offers = {}
        finalists = set()
        best = {
            arm: {
                (bound, name): np.full(len(nums), np.inf)
                for bound in (15, 30)
                for name, _, _ in folds
            }
            for arm in ARMS
        }
        positions = [search_region.latlon(packet["positions"][arm]) for arm in ARMS]
        # Stream one phase at a time; both arms share only its orbital states.
        # Each arm retains its original phase/fold accumulation order.
        for phi in phases:
            grids = phase_frequency_grids(bank, t, positions, phase_seconds=phi)
            for arm, (f, e) in zip(ARMS, grids, strict=True):
                y = np.asarray(target["corrected_hz"][arm])
                f *= q
                for name, mask, _held in folds:
                    # Uniform thinning solely for nomination, identical per policy.
                    ix = np.flatnonzero(mask)
                    ix = ix[np.unique(np.linspace(0, len(ix) - 1, min(16, len(ix))).astype(int))]
                    cost = (
                        profile_rate(
                            y[ix], f[:, ix], t[ix], rate_sigma_hz_s=0.5, bias_sigma_hz=300
                        )["cost"]
                        + (phi / 5) ** 2
                    )
                    cost = np.where(e[:, ix].min(axis=1) >= 0, cost, np.inf)
                    for bound in (15, 30):
                        if abs(phi) <= bound:
                            best[arm][bound, name] = np.minimum(best[arm][bound, name], cost)
        for arm in ARMS:
            for policy, (limit, bound, penalty) in policy_table.items():
                for name, _, _ in folds:
                    ks = top_indices(best[arm][bound, name], age, limit, penalty)
                    offers[policy, arm, name] = set(int(nums[k]) for k in ks)
                    finalists.update(offers[policy, arm, name])
        # Match candidate sets across c arms, but never across training folds.
        for policy in policy_table:
            for name, _, _ in folds:
                union = offers[policy, "c0", name] | offers[policy, "fitted_c", name]
                for arm in ARMS:
                    offers[policy, arm, name] = union
        rows = []
        for n in sorted(finalists):
            j = int(np.flatnonzero(nums == n)[0])
            for bound in (15, 30):
                pp = np.linspace(-bound, bound, int(2 * bound / 0.1) + 1)
                bb = dict(
                    time_s=grid,
                    position_km=np.broadcast_to(
                        bank["position_km"][j], (len(pp), *bank["position_km"][j].shape)
                    ),
                    velocity_km_s=np.broadcast_to(
                        bank["velocity_km_s"][j], (len(pp), *bank["velocity_km_s"][j].shape)
                    ),
                )
                for arm in ARMS:
                    relevant = [
                        (policy, penalty)
                        for policy, (limit, b, penalty) in policy_table.items()
                        if b == bound and age[j] <= limit
                    ]
                    if not relevant:
                        continue
                    f, e = paired_phase_frequency(
                        bb,
                        np.tile(t, len(pp)),
                        np.repeat(np.arange(len(pp)), len(t)),
                        pp,
                        *search_region.latlon(packet["positions"][arm]),
                    )
                    f = f.reshape(len(pp), -1) * q
                    e = e.reshape(len(pp), -1)
                    y = np.asarray(target["corrected_hz"][arm])
                    for name, train, held in folds:
                        policies = [
                            (policy, penalty)
                            for policy, penalty in relevant
                            if n in offers[policy, arm, name]
                        ]
                        if not policies:
                            continue
                        comp = components(
                            y,
                            f,
                            e[:, train].min(axis=1) >= 0,
                            t,
                            np.arange(-4, 5),
                            PERIOD,
                            mask=train,
                        )
                        m = marginal(comp, pp, 5.0)
                        if not np.isfinite(m["score"]):
                            continue
                        noise = batch_noise_screen(m["residual"][None], t)
                        row = dict(
                            arm=arm,
                            fold=name,
                            norad=n,
                            phase_limit_s=bound,
                            age_h=float(epoch[j]),
                            collection_age_h=float(collection[j]),
                            score=m["score"],
                            phase_s=m["phase_s"],
                            alias=int(m["alias_index"] - 4),
                            rms_hz=m["rms_hz"],
                            bias_hz=float(m["beta"][0]),
                            rate_hz_s=float(m["beta"][1]),
                            phase_boundary_mass=m["phase_boundary_mass"],
                            noise={k: v[0].item() for k, v in noise.items()},
                            held_rms_hz=float(np.sqrt(np.mean(m["residual"][held] ** 2)))
                            if held.any()
                            else None,
                            held_visible=bool(e[m["phase_index"], held].min() >= 0)
                            if held.any()
                            else True,
                        )
                        for policy, penalty in policies:
                            rows.append(
                                dict(
                                    row,
                                    policy=policy,
                                    score=row["score"]
                                    + (age_penalty(epoch[j]) if penalty else 0.0),
                                )
                            )
        summaries = []
        for policy in policy_table:
            pair = {}
            for arm in ARMS:
                ff = {}
                for name, _train, _held in folds:
                    rr = sorted(
                        [
                            r
                            for r in rows
                            if r["policy"] == policy and r["arm"] == arm and r["fold"] == name
                        ],
                        key=lambda r: r["score"],
                    )
                    if rr:
                        ff[name] = dict(
                            winner=rr[0],
                            runner_up=rr[1] if len(rr) > 1 else None,
                            margin=rr[1]["score"] - rr[0]["score"] if len(rr) > 1 else 0.0,
                        )
                qualified = (
                    len(ff) == 4
                    and all(v["margin"] >= 10 for v in ff.values())
                    and len({v["winner"]["norad"] for v in ff.values()}) == 1
                )
                if qualified:
                    w = ff["full"]["winner"]
                    qualified = (
                        w["noise"]["noise_screen_pass"]
                        and w["rms_hz"] <= 450
                        and abs(w["bias_hz"]) <= 3000
                        and abs(w["rate_hz_s"]) <= 2
                        and w["phase_boundary_mass"] < 0.01
                        and all(
                            v["winner"]["held_rms_hz"] <= 450 and v["winner"]["held_visible"]
                            for k, v in ff.items()
                            if k != "full"
                        )
                    )
                pair[arm] = dict(folds=ff, qualified=bool(qualified))
            accepted = all(pair[a]["qualified"] for a in ARMS)
            if accepted:
                accepted = (
                    len({pair[a]["folds"]["full"]["winner"]["norad"] for a in ARMS}) == 1
                    and len({pair[a]["folds"]["full"]["winner"]["alias"] for a in ARMS}) == 1
                )
            summaries.append(dict(policy=policy, arms=pair, screen_pass=bool(accepted)))
        outputs.append(
            dict(
                source=source,
                rows=rows,
                summaries=summaries,
                finalists=sorted(finalists),
                folds=[
                    dict(
                        name=name,
                        train_indices=np.flatnonzero(train),
                        held_indices=np.flatnonzero(held),
                    )
                    for name, train, held in folds
                ],
            )
        )
        if on_target is not None:
            on_target(deepcopy(outputs[-1]))
    return dict(
        case=packet["case"],
        targets=outputs,
        catalogue_count=len(nums),
        eligible48=int((age <= 48).sum()),
        propagation_failures=failures,
    )
