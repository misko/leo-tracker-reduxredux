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


def include_active_orbital_uncertainty(problem, bank_builder, *, families=None):
    """Retain causal orbital prior variance even for a single active owner.

    Unidentified coefficients retain their prior uncertainty under integration;
    lack of multiple owners is not evidence that the orbit is exact. The caller
    must provide a causal bank builder and call before posterior construction.
    """
    active={r['candidate_index'] for r,sl in zip(problem.rows,problem.slices,strict=True) if problem.keep[sl].any()}
    if not active<=set(problem.labels):raise ValueError('active family absent from parameter labels')
    wanted=active if families is None else set(problem.supported)|(set(families)&active)
    supported=[j for j in problem.labels if j in wanted]
    bank,metadata=bank_builder(supported)
    # Preserve the incumbent multi-owner qualification rule. New prior-only
    # coordinates must not acquire that rule merely by existing in the design.
    owner_gate=set(getattr(problem,'orbital_owner_gate_families',problem.supported))
    problem.supported=supported
    problem.supported_local=[problem.labels.index(j) for j in supported]
    problem.mode_bank=bank;problem.mode_metadata=metadata
    problem.orbital_owner_gate_families=owner_gate
    problem.orbital_uncertainty_policy=('causal prior for every active family' if families is None
                                       else 'causal prior for requested active families')
    return problem


def requires_multiple_orbital_owners(problem, family):
    """Existing learned-mode qualification, distinct from added prior variance."""
    return family in problem.supported and family in getattr(
        problem,'orbital_owner_gate_families',problem.supported)


def include_predictive_orbital_uncertainty(problem,bank_builder,families):
    """Supply prior-only orbit variance to explicitly named predictive families.

    These families need not have active curved rows. No observation mask or
    calibration mean is changed, and incumbent owner qualifications remain.
    """
    requested=set(families)
    if not requested<=set(problem.labels):raise ValueError('predictive family missing from causal design')
    supported=[j for j in problem.labels if j in set(problem.supported)|requested]
    bank,metadata=bank_builder(supported)
    owner_gate=set(getattr(problem,'orbital_owner_gate_families',problem.supported))
    problem.supported=supported;problem.supported_local=[problem.labels.index(j) for j in supported]
    problem.mode_bank=bank;problem.mode_metadata=metadata;problem.orbital_owner_gate_families=owner_gate
    problem.predictive_orbital_prior_families=sorted(requested)
    return problem
