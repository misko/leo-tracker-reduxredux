"""Conditional shared receiver-drift diagnostic; no location reference is read."""
import json
from pathlib import Path

import numpy as np
from scipy.special import gammaln

from run import (
    HERE, REPORTS, LIGHT_KM_S, REFERENCE_RF_HZ, TleArchiveReader,
    exclude_labelled_starlink_debris, parse_element_sets, propagate_candidate_states,
    robust_scores, site,
)
from robust import fit_offset


def density(residual):
    z = residual / 100.
    return gammaln(2.5)-gammaln(2)-.5*np.log(4*np.pi)-np.log(100.)-2.5*np.log1p(z*z/4)


def fit_drift(rows):
    """Alternate training-only track offsets and one normalized CFO slope per RX."""
    slopes = {rx: 0. for rx in {r['receiver_id'] for r in rows}}
    for _ in range(100):
        offsets = [float(fit_offset((r['residual']-slopes[r['receiver_id']]*r['time'])[r['mask']])) for r in rows]
        before = dict(slopes)
        for rx in slopes:
            numerator = denominator = 0.
            for r, offset in zip(rows, offsets, strict=True):
                if r['receiver_id'] != rx:
                    continue
                x = r['time'][r['mask']]
                y = r['residual'][r['mask']] - offset
                z = (y-slopes[rx]*x)/100.
                w = 5/(4+z*z)
                numerator += float(np.sum(w*x*y))
                denominator += float(np.sum(w*x*x))
            slopes[rx] = numerator / denominator
        if max(abs(slopes[k]-before[k]) for k in slopes) < 1e-8:
            break
    offsets = [float(fit_offset((r['residual']-slopes[r['receiver_id']]*r['time'])[r['mask']])) for r in rows]
    return slopes, offsets


def main():
    protocol = json.loads((HERE/'protocol.json').read_text())
    outcomes = []
    for name in protocol['inputs']:
        data = json.loads((REPORTS/'2026_09_27_ds6_common_rate_validation'/name).read_text())
        stage = json.loads((HERE/name.replace('-plan', '')).read_text())['stages'][-1]
        best = stage['best']
        archive = TleArchiveReader(Path('/var/lib/leo/tle'))
        snap = archive.select_latest_before(data['start_utc_ns']-505_000_000_000)
        assert snap.digest == data['snapshot_digest']
        payload, _ = exclude_labelled_starlink_debris(archive.read(snap))
        cat = parse_element_sets(payload)
        rec, up = site(best['latitude'], best['longitude'])
        rows = []
        for t in data['tracks']:
            if t['track_id'] not in stage['shortlists']:
                continue
            times = np.array(t['times_s']); mask = np.array(t['training_mask'], dtype=bool)
            pos, vel, ids = propagate_candidate_states(cat, np.array(stage['shortlists'][t['track_id']]),
                data['start_utc_ns'], times, np.array([best['map_time_s']]))
            unit = pos[:,0]-rec; unit /= np.linalg.norm(unit,axis=-1)[...,None]
            pred = -REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel[:,0],axis=-1)
            residual = np.array(t['measured_hz'])[None,:]-pred
            score = np.where(np.any((unit@up)[:,mask]>=0,axis=-1),robust_scores(residual,mask)[0],-np.inf)
            candidate = int(np.argmax(score))
            rows.append(dict(receiver_id=t['receiver_id'], track_id=t['track_id'],
                residual=residual[candidate],time=times-times[mask].mean(),mask=mask,
                candidate=str(cat.satellite_numbers[ids[candidate]])))
        slopes, offsets = fit_drift(rows)
        totals = dict(train_before=0.,train_after=0.,held_before=0.,held_after=0.)
        for r, offset in zip(rows,offsets,strict=True):
            base = r['residual']-fit_offset(r['residual'][r['mask']])
            adjusted = r['residual']-offset-slopes[r['receiver_id']]*r['time']
            for key,mask in [('train',r['mask']),('held',~r['mask'])]:
                totals[key+'_before'] += float(density(base[mask]).sum())
                totals[key+'_after'] += float(density(adjusted[mask]).sum())
        outcome = dict(session_id=data['session_id'],slope_hz_s=slopes,**totals,
            held_log_score_change=totals['held_after']-totals['held_before'])
        outcomes.append(outcome);print(json.dumps(outcome),flush=True)
    (HERE/'clock-audit.json').write_text(json.dumps(dict(
        scope='Conditional training-MAP identities and inferred locations; effective normalized receiver CFO drift, not a hardware calibration',
        results=outcomes),indent=2)+'\n')


if __name__ == '__main__':
    main()
