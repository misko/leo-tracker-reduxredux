"""Read-only adapter: matched probe evidence for an empirical receiver sky map.

Print JSON to stdout; never writes capture/analysis data. Executed with read
access to the installed immutable tracking port and legacy source receipts.
No IQ recomputation, association selection, timing or calibration fit.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent / '2026_10_04_ds13_18_scan_benchmark'
INPUT = Path('/srv/bulk/leo/t1-at-v1-subset-positions-20261004')
RAW = Path('/srv/bulk/leo/ds13-18scan-benchmark-20261004/inputs-v2')
RELEASE = Path('/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/lib/python3.14/site-packages')
LEGACY = Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
ALIAS = 1e6 / 4.4


def digest(path):
    return 'sha256:' + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, expected):
    assert digest(path).removeprefix('sha256:') == expected.removeprefix('sha256:'), str(path)


def compatible(p0, p1):
    fields = ('channel', 'edge', 'rf_hz', 'start_counter')
    return all(p0[k] == p1[k] for k in fields)


def pair_category(satellite, keys, detections, ambiguous, failed):
    found = [satellite in detections.get(k, set()) for k in keys]
    if not any(found): return None
    if any(not found[r] and (keys[r] in failed or satellite in ambiguous.get(keys[r], set())) for r in (0, 1)):
        return None
    return 2 if all(found) else 0 if found[0] else 1


def candidates(scan, raw_root=RAW):
    """Reconstruct predictions from frozen original calibration, all alternatives."""
    sys.path.insert(0, str(BENCH))
    from numeric_data import enable_research_model
    enable_research_model()
    if scan.startswith('N'):
        from discovery import FoldCalibration
        cal = FoldCalibration(raw_root / scan / 'seed-timing-v6')
        d = cal.data
        records = json.loads((raw_root / scan / 'seed-timing-v6/observations.json').read_text())['records']
        refined = json.loads((raw_root / scan / 'seed-timing-v6/refinement/refined.json').read_text())['records']
        metadata = {r['row_index']: r for r in records}
        status = {r['row_index']: r['refinement']['status'] == 'refined' for r in refined}
        parts = [(dest, part, models) for dest, part, models in cal.parts]
        inverse = cal.inverse
    else:
        sys.path.insert(0, str(LEGACY))
        import greedy_pool_two_scans as old
        sys.path.insert(0, str(old.OLD))
        from absolute_timing_solver import AbsoluteCalibration
        old.SCAN = scan
        cal = AbsoluteCalibration()
        d = cal.d
        ref = LEGACY / ('full-scan-A-refinement/refined.json' if scan == 'A' else 'position-top-2km/B-refinement/refined.json')
        saved = json.loads(ref.read_text())
        for p, h in saved['sources'].items():
            verify(p, h)
        refined = {r['row_index']: r for r in saved['records']}
        d.measured = np.array([refined[int(i)]['output_hz'] for i in d.original_rows])
        d.margin = np.array([refined[int(i)]['refinement'].get('margin', refined[int(i)]['original_margin']) for i in d.original_rows])
        status = {i: r['refinement']['status'] == 'refined' for i, r in refined.items()}
        bundle = HERE.parent / '2026_10_02_ds13_timing_em/scans' / old.SESSIONS[scan] / 'bundle.json'
        entries = json.loads(bundle.read_text())['alias_grouping']['representative_rows']
        metadata = {i: r for i, r in enumerate(entries)}
        parts, cursor = [], 0
        for part, models in cal.parts:
            parts.append((np.arange(cursor, cursor + len(part.times)), part, models))
            cursor += len(part.times)
        inverse = np.arange(len(d.times))
        cal.sources.update({str(ref): digest(ref), str(bundle): digest(bundle)})
    return cal, d, metadata, status, parts, inverse


def run(scan, probes_path, *, input_root=INPUT, raw_root=RAW, cohort_path=BENCH/'cohort-v2.json'):
    from east_west_sanity import enu_frame
    from prediction_jacobian import paired_prediction_jacobian
    meta_path = input_root / scan / 'input.json'
    input_path = meta_path.with_suffix('.npz')
    meta = json.loads(meta_path.read_text())
    verify(input_path, meta['input_sha256'])
    with np.load(input_path, allow_pickle=False) as z:
        frozen = {k: z[k].copy() for k in z.files}
    probes = json.loads(probes_path.read_text())
    assert probes['scan'] == scan and probes['probe_ms'] == 20
    inventory = {tuple(r['key']): r for r in probes['probes']}
    assert len(inventory) == len(probes['probes'])
    cal, d, metadata, status, parts, inverse = candidates(scan, raw_root)
    selected = frozen['numbers']
    columns = np.array([int(np.flatnonzero(d.numbers == n)[0]) for n in selected])
    shifts = frozen['initial'][6:]
    candidate_keys = [tuple(metadata[int(i)]['probe_key']) for i in d.original_rows]
    assert all(k in inventory for k in candidate_keys)
    assert all(int(rx) == k[1] and int(ch) == inventory[k]['channel'] for k, rx, ch in zip(candidate_keys, d.receiver, d.channel))
    epoch_delta = np.array([abs(t - inventory[k]['center_s']) for t, k in zip(d.times, candidate_keys)])
    assert np.max(epoch_delta) < .025, float(np.max(epoch_delta))
    starts = {int(n): (float(frozen['times'][frozen['owners'] == n].min()) - 2.,
                       float(frozen['times'][frozen['owners'] == n].max()) + 2.) for n in selected}
    predictions = {}
    for arm in ('fitted-c', 'zero-c'):
        size = sum(len(part.times) for _, part, _ in parts)
        pp, vv = np.zeros((size, len(columns))), np.zeros((size, len(columns)), bool)
        for destination, part, models in parts:
            parameters, _, correction = models[arm]
            trial = parameters.copy(); trial[6 + columns] = shifts
            rows = np.repeat(np.arange(len(part.times)), len(columns))
            sats = np.tile(columns, len(part.times))
            p, v, _ = paired_prediction_jacobian(part, trial, rows, sats)
            pp[destination] = p.reshape(len(part.times), -1) + correction[:, None]
            vv[destination] = v.reshape(len(part.times), -1)
        predictions[arm] = (pp[inverse], vv[inverse])
    # Verify reconstruction of the historical selected fitted-c assignments.
    association = meta.get('association_source') or next(p for p in meta['sources'] if p.endswith('/fitted-c.json'))
    result = json.loads(Path(association).read_text())
    if 'association_sha256' in meta: verify(association, meta['association_sha256'])
    lookup = {int(r): i for i, r in enumerate(d.original_rows)}
    sat_lookup = {int(n): j for j, n in enumerate(selected)}
    differences = []
    for a in result['final']['assignments']:
        i, j = lookup[a['row_index']], sat_lookup[a['catalog_number']]
        residual = (d.measured[i] - predictions['fitted-c'][0][i, j] + ALIAS / 2) % ALIAS - ALIAS / 2
        differences.append(abs(residual - a['residual_hz']))
    assert max(differences) < 1e-5, max(differences)
    cohort = json.loads(cohort_path.read_text())
    bound = next(r for r in cohort['scans'] if r['label'] == scan)
    pose_path = Path(bound['pose_path']); pose = json.loads(pose_path.read_text())
    assert pose['session_id'] == probes['session_id'] == bound['session_id']
    assert pose['binding_digest'] == bound['pose_binding_digest']
    authority = pose['pose_authority']
    canonical=lambda value: json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    assert 'sha256:'+hashlib.sha256(canonical(authority)).hexdigest()==pose['pose_authority_digest']
    assert 'sha256:'+hashlib.sha256(canonical({k:v for k,v in pose.items() if k!='binding_digest'})).hexdigest()==pose['binding_digest']
    assert pose['manifest_sha256']==probes['capture_sha256']
    assert authority['fixture_part_id']=='LT3D-004B'
    observer, rotation = enu_frame(authority['latitude_deg'], authority['longitude_deg'])
    good = np.array([status[int(i)] for i in d.original_rows]) & np.isfinite(d.measured) & (d.margin > 0)
    winner = {}
    for i, key in enumerate(candidate_keys):
        if key not in winner or (d.margin[i], -int(d.original_rows[i])) > (d.margin[winner[key]], -int(d.original_rows[winner[key]])):
            winner[key] = i
    top_rows = set(winner.values())
    # Candidate support epochs are ~19 ms long within the actual 20 ms probes.
    # Use the candidate's own epoch for Doppler; common probe center for sky.
    pairing = {}
    for key, p in inventory.items():
        pairing.setdefault((key[0], key[2]), {})[key[1]] = p
    events, counts = [], {}
    for arm, (prediction, visible) in predictions.items():
        error = abs((d.measured[:, None] - prediction + ALIAS / 2) % ALIAS - ALIAS / 2)
        for j, n in enumerate(selected):
            lo, hi = starts[int(n)]
            visible[:, j] &= (d.times >= lo) & (d.times <= hi)
        for gate in (300., 600.):
            possible = (error <= gate) & visible
            unique = possible.sum(axis=1) == 1
            detections, ambiguous, failed, top = {}, {}, set(), {}
            for i, key in enumerate(candidate_keys):
                if not good[i]:
                    failed.add(key)
                    continue
                js = np.flatnonzero(possible[i])
                if unique[i]:
                    detections.setdefault(key, set()).add(int(js[0]))
                    if i in top_rows:
                        top.setdefault(key, set()).add(int(js[0]))
                elif len(js):
                    ambiguous.setdefault(key, set()).update(map(int, js))
            stats = dict(missing_peer=0, mismatched_probe=0, uncertain_peer=0,
                         retained=0, outcomes=[0, 0, 0], all_alternative_promotions=0)
            for pair, pair_probes in pairing.items():
                if set(pair_probes) != {0, 1}:
                    stats['missing_peer'] += 1; continue
                p0, p1 = pair_probes[0], pair_probes[1]
                if not compatible(p0, p1):
                    stats['mismatched_probe'] += 1; continue
                keys = [(pair[0], rx, pair[1]) for rx in (0, 1)]
                found = [detections.get(k, set()) for k in keys]
                for j in found[0] | found[1]:
                    category = pair_category(j, keys, detections, ambiguous, failed)
                    if category is None:
                        stats['uncertain_peer'] += 1; continue
                    time_s = p0['center_s']
                    t = time_s + shifts[j]
                    assert frozen['nodes'][0] <= t <= frozen['nodes'][-1]
                    xyz = np.array([np.interp(t, frozen['nodes'], frozen['position'][j, :, axis]) for axis in range(3)])
                    los = xyz - observer; unit = rotation @ los / np.linalg.norm(los)
                    if unit[2] < 0: continue
                    top_category = 2 if all(j in top.get(k, set()) for k in keys) else 0 if j in top.get(keys[0], set()) else 1 if j in top.get(keys[1], set()) else -1
                    events.append(dict(scan=scan, arm=arm, gate_hz=gate, visit=pair[0], probe=pair[1],
                        satellite=int(selected[j]), channel=p0['channel'], time_s=time_s,
                        outcome=category, top_candidate_outcome=top_category,
                        east=float(unit[0]), north=float(unit[1]), up=float(unit[2])))
                    stats['retained'] += 1; stats['outcomes'][category] += 1
                    stats['all_alternative_promotions'] += category == 2 and top_category != 2
            counts[f'{arm}-{int(gate)}'] = stats
    return dict(scan=scan, events=events, counts=counts, candidate_count=len(d.times),
        unique_probes=len(set(candidate_keys)), all_scheduled_probes=len(inventory),
        failed_refinement_candidates=int(np.sum(~good)),
        reconstruction_max_hz=max(differences), sample_rate_hz=probes['sample_rate_hz'],
        maximum_candidate_probe_epoch_difference_s=float(np.max(epoch_delta)),
        sources={str(input_path): digest(input_path), str(meta_path): digest(meta_path),
                 str(probes_path): digest(probes_path), str(association): digest(association),
                 str(pose_path): digest(pose_path), **cal.sources},
        scope=__doc__, timing='Frozen absolute association timing, same in both RF arms.',
        caveat='Original five-fold calibrations retained; no new folds. A/B original Doppler identity fits used the old reference site; sky geometry is reprojected at capture-bound roof, not a new identity fit.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('scan'); p.add_argument('probes', type=Path)
    args = p.parse_args()
    sys.path.insert(0, str(BENCH))
    from numeric_data import enable_research_model
    enable_research_model()
    print(json.dumps(run(args.scan, args.probes), allow_nan=False))
