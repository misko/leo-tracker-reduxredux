"""Choose physical correction complexity from active curved evidence only."""


def restrict_to_active_orbital_support(problem):
    """Keep three-mode corrections only for two active receiver/channel owners.

    Phase coordinates, data, aliases, priors and the precomputed mode bank are
    preserved. Call before constructing any design-dependent posterior wrapper.
    Predictive linear observations deliberately cannot supply calibration support.
    This is an opt-in model change, not permission to bypass residual gates.
    """
    owners = {}
    for row, member, sl in zip(problem.rows, problem.members, problem.slices, strict=True):
        if problem.keep[sl].any():
            track = problem.scan.tracks[member]
            owners.setdefault(row["candidate_index"], set()).add(
                (track["receiver"], track["channel"])
            )
    previous = list(problem.supported)
    problem.supported = [j for j in previous if len(owners.get(j, ())) >= 2]
    problem.supported_local = [problem.labels.index(j) for j in problem.supported]
    problem.orbital_support_backoff = {
        "disabled_families": [j for j in previous if j not in problem.supported],
        "active_owners": {j: sorted(owners.get(j, ())) for j in problem.labels},
    }
    return problem
