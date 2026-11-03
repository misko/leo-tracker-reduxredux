"""Independent association and segmentation interventions on causal DSX01 data."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from compare_dsx01_frame_joint import actual_metrics
from dsx01_radial_restarts import aliases_at_start, assignment_changes
from investigate_dsx01_localization_failures import (
    OUTPUT,
    DiagnosticNormal,
    context,
    fit,
    refreshed,
)
from iterate_dsx01_profiled_identity import explore
from localize_merged_track_catalogue import raw_curvature
from run_dsx01_clean_region import reference_state, zero_state
from run_dsx01_joint_descent import ARMS, CASES, hypothesis_bank, signature

from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def hypotheses(case):
    scan, sigma, original, _, bindings, _ = context(case)
    nodes, _ = hypothesis_bank(scan, sigma)
    choices = []
    for number, node in enumerate(nodes):
        arms = {}
        for arm in ARMS:
            p, result, history = refreshed(scan, sigma, node, arm)
            arms[arm] = dict(fit=result, phase_rounds=history,
                             reference=p.reference, state=p.state(result["parameters"]))
        choices.append(dict(id=number, origin="same_scan_cold_radio_discovery", arms=arms,
                            changes=assignment_changes(original, node)))
        print(case, "refreshed hypothesis", number,
              arms["c0"]["fit"]["score"], flush=True)
    best = min(choices, key=lambda r: r["arms"]["c0"]["fit"]["score"])
    state = best["arms"]["c0"]["state"]
    anchor = np.array(best["arms"]["c0"]["fit"]["parameters"])
    seed, diagnostics = explore(scan, state, anchor, "receiver_smooth", topk=12,
                                maximum=256, compact_update=False)
    alias = aliases_at_start(scan, seed, anchor)
    candidate = dict(seed=dict(rows=seed["rows"], state=zero_state(scan)), aliases=alias)
    arms = {}
    for arm in ARMS:
        p, result, history = refreshed(scan, sigma, candidate, arm)
        arms[arm] = dict(fit=result, phase_rounds=history,
                         reference=p.reference, state=p.state(result["parameters"]))
    nodes.append(candidate)
    choices.append(dict(id=len(nodes) - 1, origin="expanded_all_catalogue_top12_max256",
                        arms=arms, changes=assignment_changes(original, candidate),
                        proposal_diagnostics=diagnostics))
    selected = min(choices, key=lambda r: r["arms"]["c0"]["fit"]["score"])
    result = dict(case=case, choices=choices, selected_id=selected["id"],
                  selected_node=nodes[selected["id"]],
                  satellite_identity_not_externally_verified=True,
                  selection="lowest full c0 objective, never position accuracy",
                  same_data_labels_aliases_other_priors_starts_budgets_for_c_pair=True,
                  candidate_generation=("same-scan cold discoveries plus "
                                        "broader causal catalogue refresh"),
                  source_bindings=bindings, GPS_used=False)
    return result


def split_track(scan, node, index, cut):
    """Undo a join without dropping or duplicating any original GLRT point."""
    old = scan.tracks[index]
    if min(cut, len(old["times"]) - cut) < 8:
        raise ValueError("both pieces require at least eight original points")
    new_scan, new_node = copy.copy(scan), copy.deepcopy(node)
    new_scan.tracks, new_scan.rx_basis = list(scan.tracks), list(scan.rx_basis)
    new_scan.curved = [i for i in scan.curved if i != index]
    new_rows, new_aliases = [], []
    row_index = next(k for k, r in enumerate(node["seed"]["rows"])
                     if r["component"] == old["key"])
    old_row = node["seed"]["rows"][row_index]
    for row, alias in zip(node["seed"]["rows"], node["aliases"], strict=True):
        if row["component"] != old["key"]:
            new_rows.append(copy.deepcopy(row))
            new_aliases.append(alias)
    for number, sl in enumerate((slice(0, cut), slice(cut, None))):
        track = dict(old, key=old["key"] + f"_part{number}")
        for key in ("times", "values", "observation_ids", "indices"):
            track[key] = old[key][sl]
        if not raw_curvature(track):
            raise ValueError("each calibration piece must retain active curvature")
        track.update(start_s=float(track["times"][0]), end_s=float(track["times"][-1]))
        new_scan.curved.append(len(new_scan.tracks))
        new_scan.tracks.append(track)
        new_scan.rx_basis.append(projected_receiver_basis(track["times"]))
        new_rows.append(dict(old_row, component=track["key"]))
        new_aliases.append(node["aliases"][row_index])
    old_ids = sorted(oid for i in scan.curved for oid in scan.tracks[i]["observation_ids"])
    new_ids = sorted(oid for i in new_scan.curved for oid in new_scan.tracks[i]["observation_ids"])
    if old_ids != new_ids or len(new_ids) != len(set(new_ids)):
        raise ValueError("segmentation must preserve one-to-one original observation ownership")
    new_node["seed"]["rows"], new_node["aliases"] = new_rows, new_aliases
    return new_scan, new_node


def segments(case):
    scan, sigma, node, _, bindings, _ = context(case)
    core = json.loads((OUTPUT / case / "core.json").read_text())
    ranked = sorted(core["track_audits"]["c0"], key=lambda r: (
        r["strongest_residual_step"]["bic_gain"] if r["strongest_residual_step"] else -1),
        reverse=True)
    selected = ranked[:3]
    selected += [r for r in ranked[3:] if r["pieces"] > 1]
    choices = []
    for row in selected:
        index = next(i for i in scan.curved if scan.tracks[i]["key"] == row["component"])
        cuts = []
        if row["strongest_residual_step"]:
            cuts.append(("largest_conditional_residual_step",
                         row["strongest_residual_step"]["cut"]))
        cuts += [("archived_piece_boundary", r["cut"]) for r in row["archived_join_tests"]]
        for kind, cut in dict.fromkeys(cuts):
            try:
                divided, divided_node = split_track(scan, node, index, cut)
            except ValueError as error:
                if "active curvature" not in str(error):
                    raise
                choices.append(dict(component=row["component"], kind=kind, cut=cut,
                                    status="ineligible", reason=str(error)))
                continue
            arms = {}
            for arm in ARMS:
                p, result, history = refreshed(divided, sigma, divided_node, arm)
                arms[arm] = dict(fit=result, phase_rounds=history,
                                 cut_search_penalty=3 * np.log(len(scan.tracks[index]["times"])),
                                 penalized_score=result["negative_twice_elbo"] + 3 * np.log(
                                     len(scan.tracks[index]["times"])))
            choices.append(dict(component=row["component"], kind=kind, cut=cut,
                                cut_time_s=float(scan.tracks[index]["times"][cut]),
                                points=len(scan.tracks[index]["times"]), arms=arms,
                                new_fragments=2, original_points_preserved=True))
            print(case, "split", row["component"], cut, flush=True)
    return dict(case=case, choices=choices, GPS_used=False, source_bindings=bindings,
                split_selection="top three residual-step BIC gains, plus every archived join",
                distinction="residual structure can arise from a wrong orbit, not only a bad join",
                score_comparison="use full normalized bounds when number of Gamma groups changes")


def combinations(case):
    # These are controlled influence probes chosen by position movement, not
    # distance to an evaluation coordinate. They are not an automatic veto.
    path = OUTPUT / case / "family.json"
    family = json.loads(path.read_text())
    scan, sigma, node, _, bindings, _ = context(case)
    core = json.loads((OUTPUT / case / "core.json").read_text())
    ranked = sorted((r for r in family["interventions"]
                     if r["arm"] == "c0" and r["phase"] == "refreshed"),
                    key=lambda r: r["shift_km"], reverse=True)[:3]
    selected = [r["target"] for r in ranked]
    p0 = DiagnosticNormal(scan, node, sigma, False)
    tests = [(selected[a], selected[b]) for a in range(3) for b in range(a + 1, 3)]
    tests.append(tuple(selected))
    rows = []
    for deleted in tests:
        keep = np.ones(len(p0.values), bool)
        for k, row in enumerate(p0.rows):
            if str(row["candidate_norad"]) in deleted:
                keep[p0.slices[k]] = False
        for arm in ARMS:
            p = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", keep=keep,
                                 reference=core["arms"][arm]["reference"])
            rows.append(dict(deleted_satellites=deleted, arm=arm, fit=fit(p),
                             deleted_points=int((~keep).sum())))
    return dict(case=case, interventions=rows, GPS_used=False, source_bindings=bindings,
                targets_selected_by="largest leave-family-out position shifts, not GPS error")


def local_candidates(incumbent, donors):
    """Recombine only actual radio-nominated identities, preserving all points."""
    original = {r["component"]: r for r in incumbent["seed"]["rows"]}
    result, seen = [], {signature(incumbent)}
    for donor in donors:
        replacements = {r["component"]: (r, alias) for r, alias in zip(
            donor["seed"]["rows"], donor["aliases"], strict=True)}
        groups = {}
        for row, alias in zip(incumbent["seed"]["rows"], incumbent["aliases"], strict=True):
            key = row["component"]
            r, a = replacements[key]
            if (r["candidate_index"], a) != (row["candidate_index"], alias):
                groups.setdefault(row["candidate_index"], []).append(key)
        moves = [keys for keys in groups.values()]
        moves += [[k] for keys in groups.values() if len(keys) > 1 for k in keys]
        for keys in moves:
            node = copy.deepcopy(incumbent)
            for index, row in enumerate(node["seed"]["rows"]):
                if row["component"] in keys:
                    replacement, alias = replacements[row["component"]]
                    row.update(candidate_index=replacement["candidate_index"],
                               candidate_norad=replacement["candidate_norad"])
                    node["aliases"][index] = alias
            identity = signature(node)
            if identity not in seen:
                if {r[0] for r in identity} != set(original):
                    raise ValueError("identity move changed the observation population")
                seen.add(identity)
                result.append(node)
    return result


def coordinate(case, maximum=12, passes=2):
    path = OUTPUT / case / "hypotheses.json"
    blob = path.read_bytes()  # Explicitly bound current-run, GPS-free continuation receipt.
    data = json.loads(blob)
    if data.get("GPS_used") is not False:
        raise ValueError("association receipt must not use GPS")
    scan, sigma, original, _, bindings, _ = context(case)
    bindings[str(path)] = hashlib.sha256(blob).hexdigest()
    donors, _ = hypothesis_bank(scan, sigma)
    current = data["selected_node"]
    arms = next(r["arms"] for r in data["choices"] if r["id"] == data["selected_id"])
    seed, detail = explore(scan, reference_state(arms["c0"]["state"]),
                           arms["c0"]["fit"]["parameters"],
                           "receiver_smooth", topk=12, maximum=256, compact_update=False)
    donors.append(dict(seed=dict(rows=seed["rows"], state=zero_state(scan)),
                       aliases=aliases_at_start(scan, seed, arms["c0"]["fit"]["parameters"])))
    history = []
    for epoch in range(passes):
        candidates = local_candidates(current, donors)
        pool = []
        state, anchor = arms["c0"]["state"], arms["c0"]["fit"]["parameters"]
        for number, node in enumerate(candidates):
            labels = sorted({r["candidate_index"] for r in node["seed"]["rows"]})
            p = DiagnosticNormal(scan, node, sigma, False,
                                 reference=np.array(state["phases"])[labels])
            residual = p.residual(anchor)
            pool.append(dict(id=number, screening_score=float(residual @ residual)))
        chosen = sorted(pool, key=lambda r: r["screening_score"])[:maximum]
        tested = []
        for row in chosen:
            node = candidates[row["id"]]
            fits = {}
            for arm in ARMS:
                p, result, rounds = refreshed(scan, sigma, node, arm)
                fits[arm] = dict(fit=result, reference=p.reference,
                                 state=p.state(result["parameters"]), phase_rounds=rounds)
            tested.append(dict(**row, arms=fits, changes=assignment_changes(current, node),
                               labels={r["component"]: r["candidate_norad"]
                                       for r in node["seed"]["rows"]}))
        best = min(tested, key=lambda r: r["arms"]["c0"]["fit"]["score"]) if tested else None
        improved = best is not None and best["arms"]["c0"]["fit"]["score"] < (
            arms["c0"]["fit"]["score"] - 1e-4)
        history.append(dict(epoch=epoch, incumbent_score=arms["c0"]["fit"]["score"],
                            screening=pool, tested=tested, improved=improved,
                            accepted_id=best["id"] if improved else None))
        if not improved:
            break
        current, arms = candidates[best["id"]], best["arms"]
        print(case, "coordinate", epoch, arms["c0"]["fit"]["score"], flush=True)
    return dict(case=case, selected_node=current, arms=arms, history=history,
                changes=assignment_changes(original, current), GPS_used=False,
                source_bindings=bindings, expanded_catalogue_proposal=detail,
                selection="full c0 objective, no point deletion, never GPS",
                maximum_fully_refitted_candidates_per_pass=maximum, passes=passes,
                caveat=("finite full-model screening and radio-nominated alternatives, "
                        "not exhaustive identity search"))


def calibration_policy(case):
    scan, sigma, node, _, bindings, _ = context(case)
    core = json.loads((OUTPUT / case / "core.json").read_text())
    p = DiagnosticNormal(scan, node, sigma, False, reference=core["arms"]["c0"]["reference"])
    x = core["arms"]["c0"]["refreshed"]["parameters"]
    metrics = actual_metrics(p, dict(rows=p.rows, aliases=p.alias, state=p.state(x),
                                    east_north_km=x, fits=[dict(parameters=x, score=0)]), "c0", x)
    evidence = []
    for k, i in enumerate(p.members):
        t = scan.tracks[i]
        endpoint_stable = all(raw_curvature(dict(times=np.delete(t["times"], j),
                                                 values=np.delete(t["values"], j)))
                              for j in (0, len(t["times"]) - 1))
        evidence.append(dict(component=t["key"], points=len(t["times"]),
                             active_after_remeasurement=raw_curvature(t),
                             active_without_either_endpoint=endpoint_stable,
                             passes_all_association_gates=metrics["tracks"][k]["compatible"]))
    policies = {
        "remeasured_curvature": [r["active_after_remeasurement"] for r in evidence],
        "endpoint_stable_curvature": [r["active_without_either_endpoint"] for r in evidence],
        "all_RF_association_gates": [r["passes_all_association_gates"] for r in evidence],
        "stable_curvature_and_gates": [r["active_without_either_endpoint"]
                                       and r["passes_all_association_gates"] for r in evidence],
    }
    rows = []
    for name, accepted in policies.items():
        keep = np.concatenate([np.full(sl.stop - sl.start, good, bool)
                               for sl, good in zip(p.slices, accepted, strict=True)])
        for arm in ARMS:
            reference, anchor, history = np.zeros(len(p.labels)), np.zeros(2), []
            for epoch in range(5):
                model = DiagnosticNormal(scan, node, sigma, arm == "fitted_c", keep=keep,
                                         reference=reference)
                result = fit(model, anchor)
                anchor = np.array(result["parameters"])
                phase = model.state(anchor)["phases"][model.labels]
                history.append(dict(epoch=epoch, fit=result))
                reference = np.clip(phase, -15, 15)
            rows.append(dict(policy=name, arm=arm, fit=result, history=history,
                             active_points=int(keep.sum()),
                             excluded_components=[r["component"] for r, good in zip(
                                 evidence, accepted, strict=True) if not good]))
        print(case, "calibration policy", name, int(keep.sum()), flush=True)
    return dict(case=case, interventions=rows, evidence=evidence, GPS_used=False,
                source_bindings=bindings,
                rule_selection="c0 radio diagnostics only; fixed for c pair",
                purpose=("calibration membership only; excluded observations remain "
                         "available for association"),
                scores_between_different_calibration_masks_not_comparable=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--stage", choices=("hypotheses", "segments", "combinations", "coordinate",
                                            "calibration_policy"),
                        required=True)
    args = parser.parse_args()
    path = OUTPUT / args.case / f"{args.stage}.json"
    if not path.exists():
        result = globals()[args.stage](args.case)
        result.update(status="complete", code_sha256=hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest())
        write(path, result)
