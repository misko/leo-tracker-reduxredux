"""Prove the four short edits and an installed-plus-anchors view share pre-Graph rows."""

from pathlib import Path
import sys

from empty_recovery_0049 import restore_empty_lanes
from matched_donor_0049 import bind_derived, derive, replace_disagreement
from sparse_only_drop_0049 import exclude_sparse_only
import signed_cfo_time_readout as signed


SHORT_EDITS = dict(matched=derive, shifted=replace_disagreement, empty=restore_empty_lanes,
                   sparse_only=exclude_sparse_only)


def source_views(stock, sparse):
    installed, short = map(signed.opportunities, (stock, sparse))
    signed.bind_pair(stock, sparse, installed, short)
    extra, rows = [], []
    for oid, lane in installed.items():
        row, original = lane["row"], short[oid]["factor"]
        if not lane["short"] and lane["factor"] is None and original is not None:
            extra.append(dict(observation_id=oid, receiver=lane["radio"], visit=row["visit_index"],
                              counter=row["valid_start_counter"], original_sparse_tuple=original))
            row = dict(row, candidates=[original])
        rows.append(row)
    patches, counts = {}, {}
    for name, edit in SHORT_EDITS.items():
        packet, _ = edit(stock, sparse)
        selection = signed.opportunities(packet)
        changes = {oid: value["row"] for oid,value in selection.items() if value["row"] != short[oid]["row"]}
        if patches.keys() & changes.keys() or any(not short[oid]["short"] for oid in changes):
            raise ValueError("The four changes must be disjoint and stay within short opportunities")
        patches.update(changes)
        counts[name] = len(changes)
    rebuilt = [patches.get(oid, item["row"]) for oid,item in short.items()]
    if not extra or rows != rebuilt:
        raise ValueError("The two derivations must have identical native tuple arrays on every opportunity")
    recipe = dict(schema="private-0049-installed-plus-sparse-anchors-v1", scope="saved research counterfactual",
                  installed_native_sha256=signed.canonical(stock), sparse_native_sha256=signed.canonical(sparse),
                  anchors="original sparse selected winners on otherwise empty installed full-anchor lanes",
                  unchanged_opportunities=True, anchor_sha256=signed.canonical(extra), short_edit_counts=counts,
                  common_probe_arrays_sha256=signed.canonical(rows))
    chosen, custody = bind_derived(stock, rows, recipe)
    comparison, _ = bind_derived(sparse, rebuilt, recipe)
    alternatives = {}
    for label, original in (("installed", installed), ("sparse", short)):
        passed = [sum(c["passed_fractional_margin_gate"] for c in item["row"]["candidates"]) for item in original.values()]
        alternatives[label] = dict(additional_passed=sum(max(0, k-1) for k in passed),
                                   lanes_with_more_than_one=sum(k>1 for k in passed),
                                   failed=sum(len(item["row"]["candidates"])-p for item,p in zip(original.values(), passed, strict=True)))
    return chosen, comparison, dict(custody, anchors=extra, additional_candidates=alternatives,
                                   short_edit_counts=counts, exact_probe_arrays=True)


def prove_graph_rows(stock, chosen, comparison, extra, winning_observations):
    original, _ = winning_observations(stock)
    first, _ = winning_observations(chosen)
    second, _ = winning_observations(comparison)
    added = {a["observation_id"] for a in extra}
    if (first != second or [row for row in first if row["observation_id"] not in added] != original
            or len(first)-len(original) != len(added)):
        raise ValueError("The exact ordered pre-Graph proof failed on the published native inputs")
    return dict(installed_rows=len(original), both_derivations_rows=len(first), added_full_anchor_rows=len(added),
                common_ordered_rows_sha256=signed.canonical(first), installed_ordered_rows_sha256=signed.canonical(original),
                two_derivations_exact=True, equals_installed=False, graph_called=False, solver_called=False)


def derive_anchor_only(stock, sparse):
    chosen, comparison, audit = source_views(stock, sparse)
    sys.path.insert(0, str(signed.RELEASE/"src"))
    from leo.analysis import glrt_frequency_input
    from leo.analysis.localization_v3 import tracks

    for module in (tracks, glrt_frequency_input):
        path = Path(module.__file__).resolve()
        key = str(path.relative_to(signed.RELEASE))
        if signed.tag(path.read_bytes()) != "sha256:"+signed.PINS[key]:
            raise ValueError("Released pre-Graph conversion changed")
    proof = prove_graph_rows(stock, chosen, comparison, audit["anchors"], tracks.winning_observations)
    return chosen, dict(audit, graph_input=proof)
