"""Ordered conditional addition after causal residual-family screening."""

from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.residual_position import add_target, fit_pair, prediction_scan
from leo.analysis.localization_v3.residual_screen import POLICIES

ARMS = ("c0", "fitted_c")


def choose_target(screen, owners, family_count, *, policy="72h_30s"):
    """Keep the original margin/point-count/fragment ordering and family cap."""
    current = {int(n) for arm in ARMS for n in owners[arm].values()}
    options, excluded = [], []
    for target in screen["targets"]:
        summary = next(s for s in target["summaries"] if s["policy"] == policy)
        if not summary["screen_pass"]:
            continue
        winner = summary["arms"]["c0"]["folds"]["full"]["winner"]
        norad = winner["norad"]
        if norad in current:
            excluded.append(
                dict(
                    fragment_id=target["source"]["fragment_id"],
                    norad=norad,
                    reason="existing family; shared-family route unchanged",
                )
            )
            continue
        if family_count >= 2:
            excluded.append(
                dict(
                    fragment_id=target["source"]["fragment_id"],
                    norad=norad,
                    reason="exact joint-family compute cap",
                )
            )
            continue
        margin = min(v["margin"] for arm in ARMS for v in summary["arms"][arm]["folds"].values())
        if margin < 10:
            continue
        source = target["source"]
        options.append((margin, source["points"], source["fragment_id"], source, winner))
    options.sort(key=lambda row: (-row[0], -row[1], row[2]))
    decision = dict(
        excluded=excluded,
        eligible_proposals=len(options),
        status="pending" if options else "no_qualified_new_family",
    )
    return (options[0] if options else None), decision


def recover_additional(
    context_factory,
    owners,
    screen,
    catalogue,
    observations,
    *,
    family_count,
    clock,
    policy="72h_30s",
    on_arm=None,
):
    """Run the original matched control and one best new-family trial.

    The context factory must reconstruct the selected owned likelihood afresh.
    Each pair retains its original 600-second objective deadline. The caller
    still owns process cancellation; this numerical deadline is not a kill port.
    A failed control cannot authorize an addition. No location-error input exists.
    """
    if policy not in POLICIES or family_count not in (0, 1, 2):
        raise ValueError("Declared residual policy and zero to two incumbent mixtures required")
    if set(owners) != set(ARMS):
        raise ValueError("Both selected ownership maps required")
    option, decision = choose_target(screen, owners, family_count, policy=policy)
    trials, control = {}, None

    def fresh():
        context = context_factory()
        if len(context["families"]) != family_count:
            raise ValueError("Reconstructed incumbent mixture count changed")
        return context

    def sink(tag):
        return (lambda arm, row: on_arm(tag, arm, row)) if on_arm is not None else None

    if option is not None:
        control = fit_pair(
            owners, fresh(), None, deadline=clock() + 600, clock=clock, on_arm=sink("control")
        )
        _, _, fragment_id, source, winner = option
        bound = POLICIES[policy][1]
        key = f"{fragment_id}-{winner['norad']}-{bound}"
        context = fresh()
        entry = add_target(context, source, winner, catalogue, observations, owners)
        try:
            family = NewFamily(
                prediction_scan(context["scan"], bound),
                [entry],
                context["model"],
                phase_step=0.05,
                phase_limit_s=bound,
                allow_uncalibrated_label=True,
            )
            pair = fit_pair(
                owners, context, family, deadline=clock() + 600, clock=clock, on_arm=sink(key)
            )
            valid = all(v["all_checked_gates_pass"] for v in pair.values()) and all(
                v["all_checked_gates_pass"] for v in control.values()
            )
            trials[key] = dict(
                status="qualified" if valid else "rejected",
                entry=entry,
                arms=pair,
                prior=family.receipt,
            )
        except (ValueError, TimeoutError) as error:
            trials[key] = dict(status="failed_closed", entry=entry, error=str(error))
        decision.update(
            status=trials[key]["status"], trial=key, source=fragment_id, norad=winner["norad"]
        )
    return dict(
        case=screen["case"],
        decisions={policy: decision},
        trials=trials,
        control=control,
        conditional_recovery=True,
        production_changed=False,
    )
