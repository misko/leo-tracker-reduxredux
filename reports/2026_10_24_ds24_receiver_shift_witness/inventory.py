"""RF-only evidence inventory; no geographic reference or model selection."""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
sys.path.insert(0, str(OLD/'evaluation'))
from matched_controls import load_baseline, measurement_binding
from probe_ds23_graph_seeded_paths import build


def one(case):
    d = load_baseline(case)
    p = build(d, 'default', 'c0', d['arms']['c0']['phase_reference'])
    by = {}; all_ids = set(); curved = 0; predictive = 0
    def add(family, track, ids, times, role):
        nonlocal curved, predictive
        assert not (set(ids) & all_ids)
        all_ids.update(ids)
        row = by.setdefault(int(family), dict(norad=int(family), fragments=[], curved_points=0, predictive_points=0))
        row[role+'_points'] += len(ids)
        row['fragments'].append(dict(key=track['key'], receiver=track['receiver'], channel=track['channel'],
            role=role, points=len(ids), start_s=float(min(times)), end_s=float(max(times)), observation_ids=ids))
        if role == 'curved': curved += len(ids)
        else: predictive += len(ids)
    for row, member, sl in zip(p.rows, p.members, p.slices, strict=True):
        mask = p.keep[sl]
        if not mask.any(): continue
        track = p.scan.tracks[member]
        ids = [i for i, keep in zip(track['observation_ids'], mask, strict=True) if keep]
        add(p.scan.norads[row['candidate_index']], track, ids, np.asarray(track['times'])[mask], 'curved')
    for entry in d['entries']:
        track = p.scan.tracks[entry['track_index']]
        add(entry['norad'], track, list(track['observation_ids']), track['times'], 'predictive')
    families = list(by.values())
    for row in families:
        row['receivers'] = sorted({r['receiver'] for r in row['fragments']})
        row['bands'] = sorted({int(r['channel'] > 4) for r in row['fragments']})
        row['curved_receivers'] = sorted({r['receiver'] for r in row['fragments'] if r['role']=='curved'})
        row['curved_bands'] = sorted({int(r['channel'] > 4) for r in row['fragments'] if r['role']=='curved'})
    result = dict(case=case, measurement_binding=measurement_binding(d),
        baseline_sha256=d['baseline_sha256'], unique_likelihood_points=len(all_ids), curved_points=curved,
        predictive_points=predictive, families=len(families),
        curved_families=sum(r['curved_points']>0 for r in families),
        both_RX_curved_families=sum(len(r['curved_receivers'])==2 for r in families),
        both_band_curved_families=sum(len(r['curved_bands'])==2 for r in families),
        families_detail=families, origin_utc_ns=d['scan'].receipt.get('origin_utc_ns'),
        causal_cutoff_utc_ns=d['scan'].receipt.get('cutoff_utc_ns'),
        no_GPS_used=True, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    assert curved+predictive == len(all_ids)
    return result


if __name__ == '__main__':
    data = [one(case) for case in ('DS24-0017','DS24-0095')]
    (HERE/'inventory.json').write_text(json.dumps(data, indent=2)+'\n')
    print(json.dumps([{k:v for k,v in row.items() if k!='families_detail'} for row in data], indent=2))
