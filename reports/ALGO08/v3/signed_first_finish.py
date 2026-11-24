"""Try the named signed finish once, before the main ordinary pair."""

from contextlib import contextmanager
from functools import wraps
from unittest.mock import patch


@contextmanager
def binding(witness, *, fallback_binding):
    import numpy as np
    import blind_joint_finish as finish
    import lighter_joint_estimator as lighter
    from blind_joint_signed import update as qualify_and_fit
    from named_survivor_fit import clock, fit_pair, now

    original_propose, original_finish = finish.propose, finish.finish_pair
    if original_finish.__qualname__ != "binding.<locals>.paired":
        raise ValueError("Signed-first requires the existing isolated-family route")
    prepared = None
    promoted = None
    attempted = False

    @wraps(original_propose)
    def propose(inputs, *args, **kwargs):
        nonlocal prepared
        prepared = inputs
        try:
            return original_propose(inputs, *args, **kwargs)
        finally:
            prepared = None

    @wraps(original_finish)
    def paired(scan, node, keep, base, powers, means, model, entries, point, region, measured):
        nonlocal attempted, promoted
        if prepared is not None and not attempted and not measured.get("isolated_branch") and np.any(keep):
            attempted = True
            early = measured["signed_first"] = {"policy": "named_gate_on_proposed_main_roster", "pair_calls": 0}
            candidate = dict(scan=scan, node=node, keep=keep, entries=entries, means=means, powers=powers, model=model)
            audit, named_witness = {}, {}
            named = early["named_fit"] = {"status": "unqualified"}

            def fit(roster, prior):
                early["pair_calls"] += 1
                named["status"] = "started"
                return fit_pair(roster, prior, named, named_witness)

            begun = now()
            try:
                result = qualify_and_fit(prepared, candidate, audit, fit_pair=fit)
            except (ValueError, AssertionError, np.linalg.LinAlgError) as error:
                early.update(status="preflight_or_numerical_failure", reason=f"{type(error).__name__}: {error}")
            else:
                if result is not candidate:
                    promoted = result
                    witness.update(named_witness)
                    named["status"] = "accepted"
                    early.update(status="accepted", ordinary_pair="skipped_by_signed_admission")
                    measured.update(audit, named_survivor_fit=named)
                    return result, True
                early.update(status=audit["signed"]["status"], reason=audit["signed"].get("reason"))
                named["status"] = early["status"]
            finally:
                early.update(attempt_clocks=clock(begun), diagnostics=audit)
            early["ordinary_pair"] = "original_path"
        return original_finish(scan, node, keep, base, powers, means, model, entries, point, region, measured)

    with fallback_binding(witness):
        late = lighter.update

        def update(inputs, candidate, measured):
            if promoted is not None and candidate is promoted:
                measured["signed_first"]["late_fit"] = "skipped_original_named_fit"
                return candidate
            return late(inputs, candidate, measured)

        with (patch.object(finish, "propose", propose), patch.object(finish, "finish_pair", paired),
              patch.object(lighter, "update", update)):
            yield
