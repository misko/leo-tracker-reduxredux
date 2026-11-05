"""Replay an adopted likelihood from owned scientific stage data.

Incidental graph extensions are audited but never added to published ownership.
The original core likelihood and any predictive family mixtures are retained.
"""

import numpy as np

from leo.analysis.localization_v3.conditional_satellite import attach_conditional_satellite_refresh
from leo.analysis.localization_v3.event_position import cached, make_event_problem
from leo.analysis.localization_v3.gap_fragments import gap_context, source_digest
from leo.analysis.localization_v3.joint_density import two_family_phase_evidence
from leo.analysis.localization_v3.joint_recovery import joint_inputs
from leo.analysis.localization_v3.new_family import NewFamily
from leo.analysis.localization_v3.recovery_fragments import (
    inactive_fragment_context,
    original_graph_view,
)
from leo.analysis.localization_v3.recovery_inclusion import attach_recovery_predictive
from leo.analysis.localization_v3.recovery_inventory import memberships

ARMS = ("c0", "fitted_c")


def replay_view(context, inventory, protocol, annotations, observations):
    """Recreate only explicitly saved predictive views, leaving the graph intact."""
    d = dict(context)
    if protocol.get("graph_bundle_sources") or protocol.get("measurement_refinements"):
        raise ValueError("Unsupported graph bundle or modified measurement incumbent")
    inactive = protocol.get("inactive_fragment_sources", [])
    native = protocol.get("native_sources", [])
    if inactive and native:
        raise ValueError("Cannot mix inactive and native incumbent views")
    if len(annotations) != len(inactive or native):
        raise ValueError("One owned annotation required per appended incumbent view")
    for annotation in annotations:
        target = annotation["protocol"]["target"]
        tid = annotation["result"]["track_id"]
        if native:
            source = annotation["gap_source"]
            if source_digest(source) != target["gap_source_sha256"]:
                raise ValueError("Selected gap source changed")
            d, rebuilt = gap_context(d, inventory, source, tid, observations)
        else:
            d, rebuilt = inactive_fragment_context(d, inventory, tid)
        for key in ("track_index", "component", "observation_ids"):
            if rebuilt[key] != target[key]:
                raise ValueError("Selected predictive view changed: " + key)
    return d


def reconstruct_incumbent(
    context,
    baseline_arms,
    baseline_owners,
    *,
    selection=None,
    inventory=None,
    annotations=(),
    observations=(),
):
    """Replay baseline, single-family, joint-family or conditional-gap science.

    Single/gap selection: {kind, trial}, where trial holds the owned protocol
    and arm results. Joint selection: {kind: joint, trials: {arm: {protocol,
    result}}}. Neither descriptor contains paths or legacy terminal envelopes.
    Selected arms/owners are supplied independently and checked against replay.
    """
    if set(baseline_arms) != set(ARMS) or set(baseline_owners) != set(ARMS):
        raise ValueError("Both independently selected calibration arms required")
    d = dict(context)
    entries, families, saved, conditional, protocol = list(d["entries"]), [], {}, [], {}
    kind = selection["kind"] if selection else "baseline"
    if kind in ("new_family", "shared_family", "gap_conditional"):
        trial = selection["trial"]
        protocol = trial["protocol"]
        d = replay_view(d, inventory, protocol, annotations, observations)
        if kind == "new_family":
            saved = trial["new_family"]["arms"]
            prior = protocol["family_prior"]
            families = [
                NewFamily(
                    d["scan"],
                    protocol["targets"],
                    d["model"],
                    phase_step=prior["phase_step_s"],
                    phase_limit_s=prior.get("phase_limit_s", 15),
                    allow_uncalibrated_label=True,
                )
            ]
        else:
            saved = trial["target_0"]["arms"]
            entries += protocol["targets"]
            if protocol.get("shared_satellite_refresh"):
                raise ValueError("Unsupported marginal shared refresh")
            if protocol.get("conditional_satellite_refresh"):
                conditional = [t["candidate_index"] for t in protocol["targets"]]
            elif kind == "gap_conditional":
                raise ValueError("Gap incumbent requires conditional satellite refresh")
    elif kind == "joint":
        trials = selection["trials"]
        if set(trials) != set(ARMS):
            raise ValueError("Both saved joint fits required")
        for arm in ARMS:
            saved[arm] = trials[arm]["result"]
            protocol = trials[arm]["protocol"]
        families = [
            NewFamily(
                d["scan"],
                targets,
                d["model"],
                phase_step=protocol["phase_step_s"],
                allow_uncalibrated_label=True,
            )
            for targets in protocol["targets"]
        ]
    elif kind != "baseline":
        raise ValueError("Unsupported selected incumbent kind: " + kind)
    d["entries"] = entries

    def factory(arm, reference):
        kw = {"base_problem_factory": d["problem_factory"]} if "problem_factory" in d else {}
        p = make_event_problem(
            d["scan"],
            d["node"],
            d["keep"],
            arm,
            reference,
            d["powers"],
            d["means"],
            d["model"],
            [],
            **kw,
        )
        attach_recovery_predictive(p, entries, d["powers"])
        if conditional:
            attach_conditional_satellite_refresh(p, entries, d["powers"], conditional)
        return cached(p)

    checks, problems = {}, {}
    for arm in ARMS:
        row = saved.get(arm)
        oldp, _ = d["problems"][arm]
        p = factory(arm, np.asarray(row["phase_reference"])) if row else oldp
        x = np.asarray(baseline_arms[arm]["endpoint_east_north_km"])
        expected = (
            row.get("incumbent_objective", row["negative_twice_elbo"])
            if row
            else baseline_arms[arm]["negative_twice_elbo"]
        )
        delta = float(p.calculate(x)["negative_twice_elbo"] - expected)
        if not np.isfinite(delta) or abs(delta) > 1e-4:
            raise ValueError(f"{arm} objective replay mismatch {delta}")
        predictive_score = 0.0
        if len(families) == 1:
            predictive_score = families[0].evaluate(p, x, d["powers"], entries)
        elif len(families) == 2:
            predictive_score = two_family_phase_evidence(
                *joint_inputs(families, p, x, d["powers"], entries),
                optimize_contractions=False,
            )["negative_twice_log_density"]
        elif families:
            raise ValueError("Exact two-family compute cap exceeded")
        full_delta = float(
            p.calculate(x)["negative_twice_elbo"]
            + predictive_score
            - baseline_arms[arm]["negative_twice_elbo"]
        )
        if not np.isfinite(full_delta) or abs(full_delta) > 1e-4:
            raise ValueError(f"{arm} full selected likelihood replay mismatch {full_delta}")
        _, _, _, owners = memberships(
            original_graph_view(p, protocol.get("original_graph_count", len(p.scan.index))),
            x,
            entries,
        )
        for family in families:
            for entry in family.entries:
                if set(entry["observation_ids"]) & set(owners):
                    raise ValueError("Duplicate incumbent addition")
                owners.update(dict.fromkeys(entry["observation_ids"], entry["norad"]))
        if any(owners.get(o) != n for o, n in baseline_owners[arm].items()):
            raise ValueError(f"{arm} incumbent ownership replay mismatch")
        checks[arm] = dict(
            incumbent_core_objective_difference=delta,
            full_selected_likelihood_difference=full_delta,
            associated_points=len(baseline_owners[arm]),
            incidental_unpublished_extensions_not_adopted=len(
                set(owners) - set(baseline_owners[arm])
            ),
            selected_kind=kind,
        )
        problems[arm] = p, x
    d.update(problems=problems, factory=factory, families=families, replay_checks=checks)
    return d
