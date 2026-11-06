def initial_search(scan, sigma, *, seed_budget=4, branch_budget=3, rounds=5,
                   iterations=48, on_branch=None, map_arms=None):
    """Fit matched c arms; select their common hypothesis using only the c0 score.

    Defaults are the original complete initial-search budgets. Smaller explicit
    budgets support bounded component comparisons, not production qualification.
    ``on_branch`` is an optional progress sink called after each completed pair.
    ``map_arms`` may execute the two pure fits concurrently, but must return
    their values in input order or raise. The default is ordinary serial map.
    """
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 1
           for n in (seed_budget, branch_budget, rounds, iterations)):
        raise ValueError('Positive integer search budgets required')
    half = scan.search_region.half_width_km
    proposals = ((0., 0.), (-half, -half), (-half, half), (half, -half), (half, half))
    candidates = fresh_discovery(scan, sigma, budget=seed_budget)
    best = min(candidates, key=lambda r: r['center_score'])
    nodes, seen = [], set()
    for candidate in candidates:
        key = signature(candidate)
        if key not in seen:
            nodes.append(candidate)
            seen.add(key)
    for point in proposals[1:]:
        seed, detail = explore(scan, best['seed']['state'], point, 'receiver_smooth',
                               compact_update=False)
        anchor = AnchoredFamilies(scan, seed, 'receiver_smooth', False, point)
        node = dict(seed=seed, aliases=anchor.alias, proposal_point=point,
                    candidate_hypotheses=detail['candidate_hypotheses'])
        key = signature(node)
        if key not in seen:
            nodes.append(node)
            seen.add(key)
    scored = []
    for node in nodes:
        cold = dict(seed=dict(rows=node['seed']['rows'], state=zero_state(scan)),
                    aliases=node['aliases'])
        p = NormalPosition(scan, cold, sigma, False, reference=np.zeros(len({
            r['candidate_index'] for r in cold['seed']['rows']})))
        residual = p.residual(np.zeros(2))
        scored.append((float(residual @ residual), cold))
    selected = sorted(scored, key=lambda r: r[0])[:branch_budget]
    tasks = [(index, arm) for index in range(len(selected))
             for arm in ('c0', 'fitted_c')]
    fitted = list(_map_branches(
        lambda item: fit_initial_arm(scan, sigma, selected[item[0]][1], item[1],
                                     rounds=rounds, iterations=iterations), tasks))
    if len(fitted) != len(tasks):
        raise ValueError('One result per initial branch/arm required')
    choices = []
    for index, (score, node) in enumerate(selected):
        arms = ('c0', 'fitted_c')
        pair = dict(zip(arms, fitted[2*index:2*index+2], strict=True))
        choice = dict(hypothesis=index, center_score=score, node=node, arms=pair)
        choices.append(choice)
        if on_branch is not None:
            on_branch(choice)
    winner = min(choices, key=lambda r: r['arms']['c0']['fit']['score'])
    zero = {}
    for arm in ('c0', 'fitted_c'):
        p = NormalPosition(scan, winner['node'], sigma, arm == 'fitted_c',
                           reference=np.zeros(len({r['candidate_index']
                                                   for r in winner['node']['seed']['rows']})))
        zero[arm] = fit(p, iterations=iterations)
    return dict(
        status='complete', GPS_used=False, choices=choices,
        selected_hypothesis=winner['hypothesis'], zero_phase_control=zero,
        selection='minimum refreshed c0 full frequency/prior bound; matched branch for fitted c',
        unique_RF_hypotheses=len(scored), fully_fitted_hypotheses=len(selected),
        same_observations_candidates_priors_bounds_and_budgets_in_c_pair=True,
        fresh_radio_seed_budget=seed_budget, RF_proposal_points=proposals,
        region_center=scan.search_region.center, box_width_km=scan.search_region.width_km,
        noise_sigma_hz=sigma)
