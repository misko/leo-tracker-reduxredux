"""Combine the independently frozen short-lane insertions and substitutions."""

from collections import Counter, defaultdict

import signed_cfo_time_readout as signed
from empty_recovery_0049 import restore_empty_lanes
from matched_donor_0049 import bind_derived, replace_disagreement


def restore_coverage_and_winner(stock, sparse):
    _, insertions = restore_empty_lanes(stock, sparse)
    _, replacements = replace_disagreement(stock, sparse)
    installed, original = map(signed.opportunities, (stock, sparse))
    inserted = {item["observation_id"]: item for item in insertions["inserted"]}
    replaced = {item["observation_id"]: item for item in replacements["donations"]}
    if inserted.keys() & replaced.keys() or (
        len(inserted) != insertions["inserted_count"]
        or len(replaced) != replacements["substituted"]
    ):
        raise ValueError("Require unique disjoint edited opportunities")

    probes, edits = [], []
    counts = defaultdict(Counter)
    for oid, lane in original.items():
        row, before = lane["row"], lane["factor"]
        coverage = counts[f"rx{lane['radio']}/{'short' if lane['short'] else 'anchor'}"]
        coverage["opportunities"] += 1
        coverage["original_winners"] += before is not None
        after = installed[oid]["factor"]
        edit = None
        if oid in inserted:
            if before is not None or after != inserted[oid]["installed_tuple"]:
                raise ValueError("Empty-lane receipt does not match its exact original tuples")
            edit = "inserted"
        if oid in replaced:
            if before != replaced[oid]["original"] or after != replaced[oid]["donor"]:
                raise ValueError("Shifted-winner receipt does not match its exact original tuples")
            edit = "replaced"
        if edit:
            if not lane["short"] or after is None:
                raise ValueError("Require a passed installed winner on a nonanchor opportunity")
            coverage[edit] += 1
            edits.append(dict(
                observation_id=oid, receiver=lane["radio"], visit=row["visit_index"],
                counter=lane["counter"], channel=row["channel"], rf_hz=row["actual_rf_hz"],
                edit=edit, original=before, installed=after,
            ))
            row = dict(row, candidates=[after])
        else:
            coverage["unchanged"] += 1
        probes.append(row)
    if len(edits) != len(inserted) + len(replaced):
        raise ValueError("An edited opportunity is absent from the signed sparse input")

    recipe = dict(
        schema="private-0049-empty-and-shifted-short-recovery-v1",
        scope="saved research counterfactual",
        sparse_native_sha256=signed.canonical(sparse),
        installed_native_sha256=signed.canonical(stock),
        ordered_edit_sha256=signed.canonical(edits),
        constituent_recipes={
            "inserted": insertions["recipe_sha256"], "replaced": replacements["recipe_sha256"],
        },
        unchanged_anchors=True,
        unchanged_ordinary_matches=True,
        unchanged_sparse_only=True,
        unchanged_opportunities=True,
    )
    packet, custody = bind_derived(sparse, probes, recipe)
    signed.bind_pair(sparse, packet, original, signed.opportunities(packet))
    return packet, dict(
        custody, edits=edits, coverage=counts, inserted=len(inserted), replaced=len(replaced),
        original_winners=sum(v["original_winners"] for v in counts.values()),
        derived_winners=sum(len(row["candidates"]) for row in probes),
        unchanged_lanes=len(probes)-len(edits),
    )


def interaction(sparse_error, installed_error, empty_error, shifted_error, joint_error):
    empty_gain, shifted_gain = sparse_error-empty_error, sparse_error-shifted_error
    joint_gain = sparse_error-joint_error
    return dict(
        empty_gain_m=empty_gain, shifted_gain_m=shifted_gain,
        sum_individual_gains_m=empty_gain+shifted_gain, joint_gain_m=joint_gain,
        joint_minus_sum_m=joint_gain-empty_gain-shifted_gain,
        remaining_installed_gap_m=joint_error-installed_error,
    )
