"""Pure grouped identity proposals; linear curves never calibrate receivers."""

import copy
import numpy as np

from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def fine_receiver_basis(times):
    grid = np.linspace(0., 300., 301)
    scale = (np.linalg.norm(projected_receiver_basis(grid)) /
             np.linalg.norm(projected_receiver_basis(grid, spacing_s=10., width_s=15.)))
    return scale * projected_receiver_basis(times, spacing_s=10., width_s=15.)


def curve_blocks(rows, members, slices, mask, tracks, minimum_points=24):
    groups = {}
    for k, (row, i, sl) in enumerate(zip(rows, members, slices, strict=True)):
        active = np.asarray(mask[sl], bool)
        if not active.any():
            continue
        key = (row['candidate_index'], tracks[i]['receiver'])
        groups.setdefault(key, []).append((k, i, int(active.sum())))
    result = []
    for (label, receiver), group in sorted(groups.items()):
        channels = {tracks[i]['channel'] for _, i, _ in group}
        points = sum(n for _, _, n in group)
        if len(channels) >= 2 and points >= minimum_points:
            result.append(dict(original_index=label, receiver=receiver,
                row_indices=[k for k, _, _ in group], track_indices=[i for _, i, _ in group],
                points=points, channels=sorted(channels)))
    return result


def apply_proposals(node, entries, tracks, proposals):
    changed = copy.deepcopy(node)
    predictive = copy.deepcopy(entries)
    used = set()
    for proposal in proposals:
        block = proposal['block']
        for k, alias in zip(block['row_indices'], proposal['aliases'], strict=True):
            if k in used:
                raise ValueError('overlapping receiver-family proposals')
            used.add(k)
            row = changed['seed']['rows'][k]
            if row['candidate_index'] != block['original_index']:
                raise ValueError('proposal belongs to another original family')
            row.update(candidate_index=proposal['candidate_index'], candidate_norad=proposal['norad'])
            changed['aliases'][k] = int(alias)
        for original, entry in zip(entries, predictive, strict=True):
            if (original['candidate_index'] == block['original_index'] and
                    tracks[original['track_index']]['receiver'] == block['receiver']):
                entry.update(candidate_index=proposal['candidate_index'], norad=proposal['norad'])
    return changed, predictive


def replacement_penalty(catalogue_count, changed_blocks, block_count, basis_count=2):
    """Incumbent-preserving discrete search penalty, declared before GPS scoring."""
    if catalogue_count < 2 or min(changed_blocks, block_count) < 0 or basis_count < 1:
        raise ValueError('valid discrete search dimensions required')
    return float(2 * changed_blocks * np.log(catalogue_count - 1) +
                 2 * np.log(basis_count * max(1, block_count)))


def orphan_predictive_labels(node, entries):
    present = {r['candidate_index'] for r in node['seed']['rows']}
    return sorted({e['candidate_index'] for e in entries}-present)
