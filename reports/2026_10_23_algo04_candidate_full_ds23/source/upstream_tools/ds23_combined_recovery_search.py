"""Bounded RF-only proposals on the supplied, event-aware curved posterior.

Scores are conditional screening costs, never posterior probabilities. The
caller must fit every offered hypothesis with the same observations and priors
in both calibration arms, and apply an explicit discrete family code.
"""

import copy

import numpy as np
from ds23_receiver_family_search import curve_blocks, orphan_predictive_labels
from investigate_ds23_adaptive_failures import phase_widths
from learn_ds23_causal_phase_forecast import distribution_cost
from probe_ds23_causal_phase_mean import forecast_phase_mean
from prototype_dsx01_continuous_position import latlon

from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.analysis.research.retained_track_likelihood import profile, whitening

COARSE_PHASES_S = np.unique(np.r_[np.linspace(-15., 15., 31), np.linspace(-2., 2., 17)])


def recovery_blocks(p, minimum_points=24):
    """Find multi-channel RX blocks and include their masked curved rows too."""
    blocks = curve_blocks(p.rows, p.members, p.slices, p.keep, p.scan.tracks,
                          minimum_points=minimum_points)
    for block in blocks:
        block['row_indices'] = [k for k, (row, i) in enumerate(zip(p.rows, p.members, strict=True))
                                if row['candidate_index'] == block['original_index'] and
                                p.scan.tracks[i]['receiver'] == block['receiver']]
        block['track_indices'] = [p.members[k] for k in block['row_indices']]
    return blocks


def _corrected(p, state, calculation, track_index, original_label):
    scan = p.scan
    track = scan.tracks[track_index]
    q = track['rf_hz'] / 11.5e9
    values = np.asarray(track['values'], float) - scan.hardware(track, state['beta'])
    values = values - q * scan.rx_basis[track_index] @ state['smooth'][track['receiver'] - 1]
    # Radio events are already represented by the event-aware hardware port.
    # Family events must be removed separately from the fixed proposal data.
    for event, amplitude in zip(getattr(p, 'events', []),
                                calculation.get('event_amplitudes_hz', []), strict=True):
        if event['kind'] == 'family' and event['candidate_index'] == original_label:
            values = values - q * amplitude * (track['times'] >= event['time_s'])
    return values


def _prediction_aliases(p, x, state, calculation, entries, proposal):
    block = proposal['block']
    j = proposal['candidate_index']
    scan = p.scan
    local = dict(time_s=scan.sky['time_s'], position_km=scan.sky['position_km'][[j]],
                 velocity_km_s=scan.sky['velocity_km_s'][[j]])
    aliases = {}
    for k, entry in enumerate(entries):
        if entry['candidate_index'] != block['original_index']:
            continue
        i = entry['track_index']
        track = scan.tracks[i]
        if block.get('receiver') is not None and track['receiver'] != block['receiver']:
            continue
        geometry = prepare_phase_geometry(local, track['times'], np.array([proposal['phase_s']]))
        frequency, _, _ = phase_linear_frequency(geometry, *latlon(x))
        y = _corrected(p, state, calculation, i, block['original_index'])
        terms = profile(y, track['rf_hz'] / 11.5e9 * frequency,
                        *whitening(track['times']), bias_sigma=300.)
        aliases[k] = int(terms['alias'][0])
    return aliases


def screen_blocks(p, x, powers, model, max_blocks=2):
    """Screen every causal catalogue label with one shared phase per block.

    Return ``(RX proposals, receipt, all_catalogue_means, original_entries)``.
    Receipt contains whole-family and same-label alias-refresh alternatives.
    Row aliases follow ``p.rows`` order, never track-index sorting. Predictive
    observations affect neither calibration nor the curved screening scores.
    """
    if not isinstance(max_blocks, int) or not 0 <= max_blocks <= 2:
        raise ValueError('bounded maximum of zero, one or two blocks required')
    powers = np.asarray(powers, float)
    if powers.shape != (len(p.rows),) or not np.isfinite(powers).all() or np.any(powers < 0):
        raise ValueError('one finite nonnegative power per curved row required')
    scan = p.scan
    labels = list(range(len(scan.norads)))
    widths, prior_receipts = phase_widths(scan, labels)
    means = forecast_phase_mean(prior_receipts, model['shrinkage'])
    entries = copy.deepcopy(getattr(p, 'linear_entries', []))
    rx_blocks = recovery_blocks(p)
    family_blocks = []
    for label in sorted({row['candidate_index'] for row in p.rows}):
        rows = [k for k, row in enumerate(p.rows) if row['candidate_index'] == label]
        if any(np.asarray(p.keep[p.slices[k]], bool).any() for k in rows):
            family_blocks.append(dict(original_index=int(label), receiver=None,
                                      row_indices=rows, track_indices=[p.members[k] for k in rows]))
    blocks = [dict(block, kind='receiver') for block in rx_blocks]
    blocks += [dict(block, kind='whole_family') for block in family_blocks]
    receipt = dict(blocks=[], catalogue_candidates=len(labels), coarse_phases_s=COARSE_PHASES_S,
                   refined_phase_step_s=.05, refined_phase_halfwidth_s=1.,
                   candidates_refined_per_block=3, maximum_proposed_blocks=max_blocks,
                   shared_phase_per_block=True,
                   proposal_scores_not_joint_posterior_probabilities=True,
                   phase_prior_receipts=prior_receipts, proposal_position_RF_only=np.asarray(x),
                   whole_family_proposals=[], calibrated_same_family_proposals=[])
    if not blocks or not max_blocks:
        return [], receipt, means, entries
    calculation, state = p.calculate(x), p.state(x)
    data = {}
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        track = scan.tracks[i]
        use = np.asarray(p.keep[sl], bool)
        y = _corrected(p, state, calculation, i, row['candidate_index'])
        white = None
        if use.any():
            if hasattr(p, 'point_noise'):
                sigma = np.asarray(p.point_noise[sl])[use]
                white = (np.diag(1. / sigma), float(2 * np.log(sigma / 150.).sum()))
            else:
                white = whitening(track['times'][use])
        data[k] = dict(y=y[use], times=track['times'][use], q=track['rf_hz'] / 11.5e9,
                       white=white,
                       full_y=y, full_times=track['times'])
    times = np.unique(np.concatenate([d['times'] for d in data.values() if len(d['times'])]))
    for d in data.values():
        d['ix'] = np.searchsorted(times, d['times'])
    costs = np.full((len(blocks), len(labels)), np.inf)
    phases = np.zeros_like(costs)
    for phase in COARSE_PHASES_S:
        geometry = prepare_phase_geometry(scan.sky, times, np.full(len(labels), phase))
        frequency, elevation, _ = phase_linear_frequency(geometry, *latlon(x))
        terms = {}
        for k, d in data.items():
            if d['white'] is None:
                terms[k] = np.zeros(len(labels))
            else:
                result = profile(d['y'], d['q'] * frequency[:, d['ix']], *d['white'])
                terms[k] = np.where(elevation[:, d['ix']].min(axis=1) >= 0, result['cost'], np.inf)
        prior = distribution_cost(phase - means, widths, model['multiplier'], model['nu'])
        for b, block in enumerate(blocks):
            score = sum(powers[k] * terms[k] for k in block['row_indices'] if powers[k] > 0) + prior
            improve = score < costs[b]
            costs[b, improve], phases[b, improve] = score[improve], phase
    # Rank with the cheap shared catalogue pass before refining. At most two
    # receiver blocks and two whole families receive the fine phase grid.
    shortlist = []
    for kind in ('receiver', 'whole_family'):
        indices = [b for b, block in enumerate(blocks) if block['kind'] == kind]
        def coarse_gain(b):
            old = blocks[b]['original_index']
            others = np.delete(costs[b], old)
            if not len(others) or not np.isfinite(others.min()):
                return -np.inf
            return float(costs[b, old] - others.min())
        shortlist += sorted(indices, key=lambda b: -coarse_gain(b))[:max_blocks]
    receipt['coarse_blocks'] = [dict(block=block,
                                      best_score=(float(costs[b].min())
                                                  if np.isfinite(costs[b].min()) else None),
                                      refined=b in shortlist) for b, block in enumerate(blocks)]
    receiver, whole, calibrated = [], [], []
    for b in shortlist:
        block = blocks[b]
        ordered = [int(j) for j in np.argsort(costs[b], kind='stable') if np.isfinite(costs[b, j])]
        old = block['original_index']
        nominees = [old] + [j for j in ordered if j != old][:3]
        candidates = []
        for j in nominees:
            if not np.isfinite(costs[b, j]):
                continue
            center = phases[b, j]
            grid = np.arange(max(-15., center - 1.), min(15., center + 1.) + .025, .05)
            local = dict(time_s=scan.sky['time_s'], position_km=scan.sky['position_km'][[j]],
                         velocity_km_s=scan.sky['velocity_km_s'][[j]])
            best = None
            for phase in grid:
                geometry = prepare_phase_geometry(local, times, np.array([phase]))
                frequency, elevation, _ = phase_linear_frequency(geometry, *latlon(x))
                score = float(distribution_cost(phase - means[j], widths[j],
                                                 model['multiplier'], model['nu']))
                aliases = []
                for k in block['row_indices']:
                    d = data[k]
                    if d['white'] is None:
                        # Masked rows remain present, with a coherent alias.
                        g = prepare_phase_geometry(local, d['full_times'], np.array([phase]))
                        f, _, _ = phase_linear_frequency(g, *latlon(x))
                        terms = profile(d['full_y'], d['q'] * f, *whitening(d['full_times']))
                    else:
                        terms = profile(d['y'], d['q'] * frequency[:, d['ix']], *d['white'])
                        score += powers[k] * float(terms['cost'][0])
                        if elevation[:, d['ix']].min() < 0:
                            score = np.inf
                    aliases.append(int(terms['alias'][0]))
                if np.isfinite(score) and (best is None or score < best['score']):
                    best = dict(candidate_index=j, norad=int(scan.norads[j]), score=score,
                                phase_s=float(phase), aliases=aliases)
            if best is not None:
                candidates.append(best)
        incumbent = next((c for c in candidates if c['candidate_index'] == old), None)
        other = [c for c in candidates if c['candidate_index'] != old]
        receipt['blocks'].append(dict(block=block, candidates=candidates))
        if incumbent is None and not other:
            continue
        if block['kind'] == 'whole_family' and incumbent is not None:
            calibrated.append(dict(incumbent, block=block, kind='same_family',
                                   id=f'family_{old}_same', proposal_gain=0.))
        if other:
            winner = min(other, key=lambda c: c['score'])
            offered = dict(winner, block=block, kind=block['kind'],
                           id=f"{block['kind']}_{old}_{block['receiver']}_{winner['candidate_index']}",
                           proposal_gain=(incumbent['score'] - winner['score']
                                          if incumbent else None))
            (receiver if block['kind'] == 'receiver' else whole).append(offered)
    def gain_order(record):
        return -record['proposal_gain'] if record['proposal_gain'] is not None else -np.inf
    receiver = sorted(receiver, key=gain_order)[:max_blocks]
    whole = sorted(whole, key=gain_order)[:max_blocks]
    # Refresh aliases for the same families nominated by the whole-family search.
    ranked_labels = [r['block']['original_index'] for r in whole]
    calibrated.sort(key=lambda r: (r['block']['original_index'] not in ranked_labels,
                                   ranked_labels.index(r['block']['original_index'])
                                   if r['block']['original_index'] in ranked_labels else 0))
    calibrated = calibrated[:max_blocks]
    for proposal in receiver + whole + calibrated:
        proposal['predictive_aliases'] = _prediction_aliases(
            p, x, state, calculation, entries, proposal)
    receipt['whole_family_proposals'] = whole
    receipt['calibrated_same_family_proposals'] = calibrated
    return receiver, receipt, means, entries


def recovery_alternatives(proposals, receipt):
    """Null, up to two RX singles, their simultaneous pair, and family options."""
    if len(proposals) > 2:
        raise ValueError('at most two receiver proposals required')
    alternatives = [dict(id='null', proposals=[])]
    alternatives += [dict(id=p['id'], proposals=[p]) for p in proposals]
    if len(proposals) == 2:
        alternatives.append(dict(id='receiver_pair', proposals=list(proposals)))
    for key in ('whole_family_proposals', 'calibrated_same_family_proposals'):
        alternatives += [dict(id=p['id'], proposals=[p]) for p in receipt.get(key, [])[:1]]
    return alternatives


alternatives = recovery_alternatives


def growth_offers(p, x, powers, model, max_offers=2):
    """Nominate complete rejected curved fragments from the full catalogue.

    At least 12 points over 10 seconds are required. A new satellite must have
    two distinct receiver/channel owners; otherwise it must already have
    retained curved support. Original predictive associations are untouched.
    The returned rows index the original ``p.rows`` and must be activated with
    the identical mask in both calibration arms by the caller.
    """
    if not isinstance(max_offers, int) or not 0 <= max_offers <= 2:
        raise ValueError('at most two growth offers required')
    eligible = []
    supported = set()
    for k, (row, i, sl) in enumerate(zip(p.rows, p.members, p.slices, strict=True)):
        if np.asarray(p.keep[sl], bool).any():
            supported.add(int(row['candidate_index']))
            continue
        times = p.scan.tracks[i]['times']
        if len(times) >= 12 and np.ptp(times) >= 10.:
            eligible.append(k)
    if not eligible or not max_offers:
        return []
    view = copy.copy(p)
    view.rows = [p.rows[k] for k in eligible]
    view.members = [p.members[k] for k in eligible]
    view.slices = [p.slices[k] for k in eligible]
    view.keep = np.zeros_like(p.keep, dtype=bool)
    for sl in view.slices:
        view.keep[sl] = True
    view.linear_entries = []
    _, receipt, _, _ = screen_blocks(view, x, np.asarray(powers)[eligible], model,
                                     max_blocks=max_offers)
    offered = []
    for record in receipt['blocks']:
        block = record['block']
        if block['kind'] != 'whole_family':
            continue
        rows = [eligible[k] for k in block['row_indices']]
        owners = {(p.scan.tracks[p.members[k]]['receiver'], p.scan.tracks[p.members[k]]['channel'])
                  for k in rows}
        candidates = [c for c in record['candidates']
                      if c['candidate_index'] in supported or len(owners) >= 2]
        if not candidates:
            continue
        best = min(candidates, key=lambda c: c['score'])
        updated = dict(block, row_indices=rows, track_indices=[p.members[k] for k in rows],
                       predictive_entry_indices=[])
        offered.append(dict(
            best, block=updated, kind='growth',
            id=f"growth_{block['original_index']}_{best['candidate_index']}",
            predictive_aliases={}, rows=rows,
            added_points=sum(len(p.scan.tracks[p.members[k]]['times']) for k in rows),
            new_label_supported_by_retained_curves=best['candidate_index'] in supported,
            distinct_receiver_channel_owners=len(owners),
            proposal_scores_not_joint_posterior_probabilities=True))
    return sorted(offered, key=lambda offer: offer['score'])[:max_offers]


def apply_recovery_proposals(node, entries, tracks, proposals):
    """Atomically relabel curves and predictive factors using original labels.

    Reject unsupported predictive hypotheses without removing any measurement.
    Row indices address active-curvature rows, as do the original alias arrays.
    """
    changed, predictive = copy.deepcopy(node), copy.deepcopy(entries)
    original_rows = [r for r in node['seed']['rows'] if r.get('active_curvature', True)]
    changed_rows = [r for r in changed['seed']['rows'] if r.get('active_curvature', True)]
    used_rows, used_entries = set(), set()
    for proposal in proposals:
        block = proposal['block']
        old = block['original_index']
        matching = {k for k, entry in enumerate(entries) if entry['candidate_index'] == old and
                    (block.get('receiver') is None or
                     tracks[entry['track_index']]['receiver'] == block['receiver'])}
        if 'predictive_entry_indices' in block and proposal.get('kind') != 'growth':
            raise ValueError('only unassociated growth may preserve original predictive labels')
        required = (matching if 'predictive_entry_indices' not in block
                    else set(block['predictive_entry_indices']))
        if not required <= matching:
            raise ValueError('predictive indices must belong to the original block')
        supplied = {int(k): v for k, v in proposal.get('predictive_aliases', {}).items()}
        if set(supplied) != required:
            raise ValueError('complete predictive aliases required; no observation may be dropped')
        for k, alias in zip(block['row_indices'], proposal['aliases'], strict=True):
            if k in used_rows:
                raise ValueError('overlapping recovery proposals')
            if original_rows[k]['candidate_index'] != old:
                raise ValueError('proposal belongs to another original family')
            used_rows.add(k)
            changed_rows[k].update(candidate_index=int(proposal['candidate_index']),
                                   candidate_norad=int(proposal['norad']))
            changed['aliases'][k] = int(alias)
        for k, alias in supplied.items():
            if k in used_entries:
                raise ValueError('overlapping predictive proposals')
            used_entries.add(k)
            predictive[k].update(candidate_index=int(proposal['candidate_index']),
                                 norad=int(proposal['norad']), alias=int(alias))
    missing = orphan_predictive_labels(dict(seed=dict(rows=changed_rows)), predictive)
    if missing:
        raise ValueError(f'unsupported predictive families {missing}; '
                         'original observations retained')
    return changed, predictive
