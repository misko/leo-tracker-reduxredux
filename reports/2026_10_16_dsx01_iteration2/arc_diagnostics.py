"""Read-only replay of frozen A arc extraction and proposal eligibility.

No physical optimizer is run. Region/candidate hypotheses are evaluation labels
read only after generic whole-recording extraction and full-bank projection.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
MODELS = HERE.parent / '2026_10_16_dsx01_models'
DATASET = HERE.parent / '2026_10_16_dsx01_fast_association_losses'


def summarize_overlap(tracks, members):
    members = set(map(int, members))
    overlaps = [len(members.intersection(map(int, track))) for track in tracks]
    union = set().union(*(set(map(int, track)) for track in tracks)) if tracks else set()
    order = sorted(range(len(tracks)), key=lambda k: (-overlaps[k], k))[:5]
    return dict(covered=len(members & union), total=len(members),
        best_overlap=max(overlaps, default=0), overlapping_arcs=sum(n > 0 for n in overlaps),
        best_arcs=[dict(rank=k+1, points=len(tracks[k]), overlap=overlaps[k],
                        rows=np.asarray(tracks[k]).tolist()) for k in order if overlaps[k]])


def arc_profile(observations, correction, bank, prior, vector, tracks, shifts, *, grid=None):
    """Reproduce A's existing declared grid; all candidates are evaluated equally."""
    from leo.analysis.hard60_score import predict_orbits
    from leo.analysis.regional_position_score import circular
    from model_a import _subset

    grid = np.arange(-8., 8.001, .25) if grid is None else np.asarray(grid)
    sampled = [track[np.linspace(0, len(track)-1, min(16, len(track))).astype(int)]
               for track in tracks]
    rows = np.unique(np.concatenate(sampled))
    selected = _subset(observations, rows)
    positions = [np.searchsorted(rows, track) for track in sampled]
    measured = observations.measured_hz[rows] - correction[rows]
    count = len(bank.numbers)

    def evaluate(tau):
        prediction, visible, _, _ = predict_orbits(bank, selected, prior, vector[:2],
                                                   tau, derivatives=False)
        rr = abs(circular(measured[:, None] - prediction))
        loss = np.array([np.mean(np.minimum((rr[ix]/125.)**2, 25.), axis=0)*len(track)
                         for track, ix in zip(tracks, positions)])
        coherent = np.array([np.mean((rr[ix] < 375.) & visible[ix], axis=0) >= .7
                             for ix in positions])
        fraction = np.array([np.mean((rr[ix] < 375.) & visible[ix], axis=0)
                             for ix in positions])
        return loss, coherent, fraction

    baseline, _, _ = evaluate(shifts)
    best_gain = np.zeros(count)
    best_shift = shifts.copy()
    support = np.zeros(count, int)
    max_fraction = np.zeros((len(tracks), count))
    for value in grid:
        loss, coherent, fraction = evaluate(np.full(count, value))
        max_fraction = np.maximum(max_fraction, fraction)
        gain = np.maximum(baseline-loss, 0.)*coherent
        totals = gain.sum(axis=0)
        take = totals > best_gain
        best_gain[take] = totals[take]
        best_shift[take] = value
        support[take] = np.sum(coherent[:, take] & (gain[:, take] > 0), axis=0)
    ranks = np.empty(count, int)
    ranks[np.argsort(-best_gain, kind='stable')] = np.arange(1, count+1)
    return dict(candidate_numbers=bank.numbers.tolist(), gains=best_gain.tolist(),
                shifts=best_shift.tolist(), supporting_arcs=support.tolist(),
                ranks=ranks.tolist(), max_coherent_fraction=max_fraction.tolist(),
                sampled_rows=rows.tolist(), projection_calls=1+len(grid))


def load_saved_source(source):
    """Restore public numerical inputs; reuse correction exports when available."""
    from leo.contracts.regional_position import PositionObservations, PositionOrbitBank, RegionalPrior
    from common import load_context
    from model_a import _correction

    folder = HERE.parents[1] / source['report_directory']
    original = json.loads((MODELS/'results'/f"{source['source_id']}-full-fitted-c-original.json").read_text())
    if not (folder/'baseline.npz').exists():
        ctx = load_context(source['source_id'])
        correction = _correction(ctx.model, ctx.vector, ctx.nuisance)
        shifts = ctx.vector[7]+ctx.model.basis@ctx.vector[8:]
        return ctx.observations, correction, ctx.bank, ctx.prior, ctx.vector, shifts
    a = np.load(folder/'baseline.npz')
    ctx = json.loads((folder/'context.json').read_text())
    obs = PositionObservations(tuple(ctx['window_ids']), a['times'], a['measured'], a['rf'],
                               a['receiver'], a['channel'], np.ones(len(a['times'])))
    b = np.load(folder/'orbit-bank.npz')
    bank = PositionOrbitBank(b['numbers'], b['nodes'], b['positions'], b['velocities'])
    numbers = original['full_scan']['total_timing_s']
    order = {int(n): k for k,n in enumerate(bank.numbers)}
    bank = bank.select([order[int(n)] for n in numbers])
    vector = np.asarray(original['vector'])
    shifts = np.array([numbers[str(int(n))] for n in bank.numbers])
    return obs, a['correction'], bank, RegionalPrior(**ctx['prior']), vector, shifts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', nargs='+')
    parser.add_argument('--uncapped-limit', type=int, default=512)
    args = parser.parse_args()
    sys.path.insert(0, str(MODELS))
    from common import save_json
    from model_a import extract_tracks
    sources = json.loads((DATASET/'sources.json').read_text())
    dataset = json.loads((DATASET/'dataset.json').read_text())
    findings = {x['region_id']: x for x in json.loads((DATASET/'findings.json').read_text())['regions']}
    for source in sources:
        if args.sources and source['source_id'] not in args.sources:
            continue
        begun = time.monotonic()
        obs, correction, bank, prior, vector, shifts = load_saved_source(source)
        tracks = extract_tracks(obs, np.ones(len(obs.times_s), bool), correction,
                                maximum_tracks=args.uncapped_limit,
                                deadline=time.monotonic()+45.)
        capped = tracks[:48]
        profiles = arc_profile(obs, correction, bank, prior, vector, capped, shifts)
        larger_profiles = arc_profile(obs, correction, bank, prior, vector, tracks, shifts)
        regions = []
        for region in dataset['regions']:
            if region['source_id'] != source['source_id']:
                continue
            members = np.flatnonzero((obs.receiver == region['receiver']-1) &
                (obs.channel == region['channel']) & (obs.times_s >= region['start_s']) &
                (obs.times_s <= region['end_s']))
            entry = dict(region=region, capped=summarize_overlap(capped, members),
                         larger_cap=summarize_overlap(tracks, members), candidates=[])
            for number in findings[region['region_id']]['hypothesis_satellites']:
                if number not in profiles['candidate_numbers']:
                    entry['candidates'].append(dict(satellite=number, retained=False))
                    continue
                k = profiles['candidate_numbers'].index(number)
                overlap = [len(set(map(int,tr)) & set(map(int,members))) for tr in capped]
                indices = [i for i,n in enumerate(overlap) if n]
                fractions = np.asarray(profiles['max_coherent_fraction'])[:, k]
                entry['candidates'].append(dict(satellite=number, retained=True,
                    maximum_gain=profiles['gains'][k], timing_s=profiles['shifts'][k],
                    baseline_timing_s=float(shifts[k]), rank=profiles['ranks'][k],
                    supporting_arcs=profiles['supporting_arcs'][k],
                    max_region_overlapping_arc_coherence=max((float(fractions[i]) for i in indices), default=0.),
                    eligible=bool(profiles['ranks'][k] <= 8 and profiles['gains'][k] > 25 and
                                  abs(profiles['shifts'][k]-shifts[k]) >= .2),
                    larger_cap=dict(maximum_gain=larger_profiles['gains'][k],
                        timing_s=larger_profiles['shifts'][k],rank=larger_profiles['ranks'][k],
                        supporting_arcs=larger_profiles['supporting_arcs'][k],
                        eligible=bool(larger_profiles['ranks'][k] <= 8 and
                            larger_profiles['gains'][k] > 25 and
                            abs(larger_profiles['shifts'][k]-shifts[k]) >= .2))))
            regions.append(entry)
        result = dict(source_id=source['source_id'], kind='read-only-frozen-A-arc-replay',
            track_count=len(tracks), capped_track_count=len(capped),
            track_rows=[tr.tolist() for tr in tracks], profiles=profiles,
            larger_cap_profiles=larger_profiles, regions=regions,
            elapsed_seconds=time.monotonic()-begun,
            qualification='Existing-grid projections only; no physical optimizer/refit. '
            'Window/candidate hypotheses are diagnostic evaluation labels, not extraction inputs.')
        save_json(HERE/f"arc_diagnostics_{source['source_id']}.json", result)
        print(json.dumps(dict(source_id=source['source_id'], track_count=len(tracks),
            regions=[dict(id=x['region']['region_id'], capped=x['capped']['covered'],
                          larger=x['larger_cap']['covered'], candidates=x['candidates']) for x in regions])),flush=True)


if __name__ == '__main__':
    main()
