"""Ordered final-stage nomination and receiver-shared predictive admission."""

from copy import deepcopy

from leo.analysis.localization_v3.reassociation_catalogue import prepare_catalogue
from leo.analysis.localization_v3.reassociation_guard import receiver_shared_check
from leo.analysis.localization_v3.reassociation_policy import destination_owned
from leo.analysis.localization_v3.reassociation_screen import screen
from leo.analysis.localization_v3.reassociation_uniqueness import from_additional_checks

ARMS = ("c0", "fitted_c")


def admit(context, owners, targets, catalogue, scan_receipt, *, on_target=None):
    """Nominate from causal RF evidence before any history change or replacement fit.

    The caller owns the scan's process deadline. A propagation block returns no
    partial admission. This routine cannot publish a position or collect history.
    """
    result = dict(
        status="screened",
        targets=list(targets),
        catalogue_eligibility=None,
        propagation_failures=[],
        screens={},
        shared={},
        guards={},
        admitted=[],
    )
    if not targets:
        return result
    prepared = prepare_catalogue(catalogue, scan_receipt)
    result.update(
        catalogue_eligibility=prepared["propagation"], propagation_failures=prepared["failures"]
    )
    if not prepared["eligible"]:
        result["status"] = "propagation_fallback"
        return result
    for old in targets:
        screened = screen(context, old, prepared["nums"], prepared["bank"])
        result["screens"][str(old)] = screened
        proposals = [
            h
            for h in screened.get("proposals", [])
            if "prediction_limit" not in h
            and set(map(int, h["mapping"].values())) == {int(h["norad"])}
            and int(h["norad"]) != int(old)
            and all(h["predictive"][arm]["pass_check"] for arm in ARMS)
        ]
        shared = None
        admitted = []
        for hypothesis in proposals:
            name, new = hypothesis["name"], hypothesis["norad"]
            if destination_owned(owners, new):
                result["guards"][name] = dict(
                    passed=False,
                    status="rejected",
                    model="receiver_offset",
                    reason="destination_already_owned",
                )
                continue
            if shared is None:
                shared = receiver_shared_check(
                    context, scan_receipt, screened, old, new, prepared["ledger"]
                )
                result["shared"][str(old)] = shared
            guard = from_additional_checks(dict(shared, new=new))
            result["guards"][name] = guard
            if guard["passed"]:
                admitted.append(hypothesis)
                result["admitted"].append(dict(target=old, hypothesis=hypothesis))
        if on_target is not None:
            on_target(deepcopy(dict(target=old, screen=screened, shared=shared, admitted=admitted)))
    return result
