"""Distinguish actual joined components from originals admitted by a quota change."""

from collections import Counter


def continuous_mark_groups(selected_originals, selected_merged, original_rows, components):
    """Produce disjoint parent/join groups over exactly the same observation rows.

    ``original_rows`` contains every original segment, including ones outside
    the baseline bootstrap quota. Such a segment is never inferred to be a join
    solely because it appears only in the merged bootstrap selection.
    Components carry explicit parent identities; unknown or ambiguous joins
    remain errors rather than being guessed by proximity.
    """
    inventory = {identity: frozenset(rows) for identity, rows in original_rows.items()}
    if any(
        not rows or any(not isinstance(r, int) or r < 0 for r in rows)
        for rows in inventory.values()
    ):
        raise ValueError("original segments must contain nonempty valid row sets")
    originals = set(inventory.values())
    baseline = {frozenset(rows) for rows in selected_originals}
    if not baseline <= originals:
        raise ValueError("selected original lacks full inventory authority")
    joined_components = []
    for members in components:
        if len(members) < 2 or len(set(members)) != len(members):
            raise ValueError("joined component requires distinct original parent identities")
        if any(member not in inventory for member in members):
            raise ValueError("joined component has unknown original parent")
        joined_components.append(
            (frozenset().union(*(inventory[m] for m in members)), tuple(members))
        )
    joins, parents, admitted = [], [], []
    for rows in selected_merged:
        rows = frozenset(rows)
        if rows in originals:
            if rows not in baseline:
                admitted.append(tuple(sorted(rows)))
            continue
        matching = [members for union, members in joined_components if union == rows]
        if len(matching) != 1:
            raise ValueError("joined proposal has missing or ambiguous explicit parent authority")
        joins.append(rows)
        parents.extend(inventory[member] for member in matching[0])
    counts = Counter(row for rows in parents for row in rows)
    ambiguous = {row for row, count in counts.items() if count > 1}
    groups = {
        "joined": [tuple(sorted(rows - ambiguous)) for rows in joins if rows - ambiguous],
        "parents": [tuple(sorted(rows - ambiguous)) for rows in parents if rows - ambiguous],
    }
    if set().union(*map(set, groups["joined"])) != set().union(*map(set, groups["parents"])):
        raise ValueError("parent and joined groups cover different evidence")
    return groups, {
        "excluded_ambiguous_rows": sorted(ambiguous),
        "newly_selected_originals": admitted,
        "actual_selected_joined_components": len(joins),
        "all_observations_retained": True,
    }
