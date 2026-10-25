"""Metadata-only complete-owner witness inventory; never reads CFO fields."""
from bisect import bisect_left
import csv
import hashlib
import json
import math
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
CASE = 'DS24-0013'
ARMS = ('c0', 'fitted_c')
INPUTS = {
    'tracks': Path('/srv/bulk/leo/research/ds25-20261024/DS24-0013/tracks.json'),
    'parent': Path('/srv/bulk/leo/research/ds25-20261024/family_cavity/position/DS24-0013.json'),
    'ownership': Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership/DS24-0013/parent.json'),
    'old_reference_inventory': Path('/srv/bulk/leo/research/ds24-next-directions-review-r01/identity/inventory.json'),
}


def read(p):
    return json.loads(Path(p).read_text())


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    with Path(p).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def metadata(track):
    times = list(map(float, track['times']))
    ids = list(track['observation_ids'])
    if not times or len(times) != len(ids) or len(ids) != len(set(ids)):
        raise ValueError('incomplete/duplicate native owner')
    if not all(map(math.isfinite, times)) or times != sorted(times):
        raise ValueError('nonfinite or unordered native times')
    rf = float(track['rf_hz'])
    if not math.isfinite(rf) or rf <= 0:
        raise ValueError('invalid RF metadata')
    return dict(component=track['key'], receiver=track['receiver'],
                channel=track['channel'], rf_hz=rf, times_s=times,
                observation_ids=ids, points=len(ids), start_s=times[0], end_s=times[-1])


def time_relation(owner, reference, grid):
    a, b = owner['start_s'], owner['end_s']
    c, d = reference['start_s'], reference['end_s']
    if max(a, c) <= min(b, d):
        return dict(relation='interval_overlap', overlap_s=min(b, d)-max(a, c), gap_s=0.)
    lo, hi = (b, c) if b < c else (d, a)
    left, right = bisect_left(grid, lo), bisect_left(grid, hi)
    if grid[left] != lo or grid[right] != hi:
        raise ValueError('owner endpoint missing from frozen time grid')
    adjacent = right == left + 1
    return dict(relation='adjacent_native_slices' if adjacent else 'separated',
                overlap_s=0., gap_s=hi-lo, intervening_native_time_slices=right-left-1)


def classify(owner, curved, accepted, reference_ids, relations):
    ids = set(owner['observation_ids'])
    overlaps = {a: sorted(ids & accepted[a]) for a in ARMS}
    reasons = []
    if owner['receiver'] != 'RX2':
        reasons.append('receiver is not RX2')
    if any(overlaps.values()):
        reasons.append('overlaps complete original accepted IDs; no trimming')
    if ids & reference_ids:
        reasons.append('reuses previously tested RX1 native IDs')
    if not any(r['relation'] in ('interval_overlap', 'adjacent_native_slices') for r in relations):
        reasons.append('no overlapping/adjacent reference time support')
    base_eligible = not reasons
    primary_reasons = list(reasons)
    if not curved:
        primary_reasons.append('not an archived canonical curved graph owner')
    return dict(original_accepted_ID_overlap=overlaps,
                reused_reference_IDs=sorted(ids & reference_ids),
                eligibility_reasons=primary_reasons, primary_eligible=not primary_reasons,
                secondary_noncurved_eligible=bool(base_eligible and not curved),
                secondary_exclusion_reasons=reasons,
                canonical_curved=curved)


def main():
    began = time.monotonic()
    # This is written BEFORE projecting any metadata or exposing any results.
    protocol = dict(case=CASE, source_sha256=sha(__file__),
        test_source_sha256=sha(HERE/'test_inventory.py'),
        input_bindings={name:dict(path=str(p),sha256=sha(p)) for name,p in INPUTS.items()},
        primary='all complete unused RX2 canonical curved graph owners; no candidate/alias/CFO fields used',
        unused='zero overlap with either arm complete original accepted-ID union, including postfit; no trimming',
        time_support='closed intervals overlap, OR disjoint nearest endpoints are consecutive distinct times in sorted union of ALL archived native-owner times; no arbitrary gap cutoff',
        RF='record exact same-carrier eligibility against each historical reference owner separately; crossband does not imply a shared transmitter offset',
        secondary='unused time-supported noncurved RX2 sources retained as predictive-only metadata; never calibrate receiver offsets/drifts',
        ordering='all eligible owners, ordered start time/channel/component; no closest-to-label choice or replacement',
        reference='previously tested four RX1 sources only define time/RF metadata; no repeat scores; historically label-selected',
        graph_extraction_response_selected=True, maximum_seconds=120.,
        target_CFO_or_candidate_closeness_read=False, position_fits=0, GPS_used=False,
        RF_comparison_authorized=False)
    write(HERE/'protocol.json',protocol)
    write(HERE/'protocol_seal.json',dict(protocol_sha256=sha(HERE/'protocol.json')))
    tracks = read(INPUTS['tracks'])
    parent, ownership = read(INPUTS['parent']), read(INPUTS['ownership'])
    assert ownership['source_parent_sha256'] == sha(INPUTS['parent'])
    assert ownership['source_tracks_sha256'] == sha(INPUTS['tracks'])
    assert parent['status'] == ownership['status'] == 'complete'
    node = parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
    curved = {r['component'] for r in node['seed']['rows'] if r['active_curvature']}
    accepted = {a:set(ownership['coverage'][a]['accepted_observation_ids']) for a in ARMS}
    old = next(r for r in read(INPUTS['old_reference_inventory'])['rows'] if r['case']==CASE)
    ref_specs = [dict(component=old['target']['component'], observation_ids=old['target']['observation_ids'])]
    ref_specs += [dict(component=r['component'], observation_ids=r['observation_ids']) for r in old['other_same_family_raw_sources']]
    owners = [metadata(t) for t in tracks]
    lookup = {r['component']:r for r in owners}
    assert len(lookup) == len(owners)
    references = [lookup[r['component']] for r in ref_specs]
    for r,spec in zip(references,ref_specs,strict=True):
        assert r['observation_ids']==spec['observation_ids'] and r['receiver']=='RX1'
    reference_ids = {i for r in references for i in r['observation_ids']}
    assert len(reference_ids)==sum(r['points'] for r in references)==189
    grid = sorted({t for r in owners for t in r['times_s']})
    rows = []
    for owner in sorted(owners,key=lambda r:(r['start_s'],r['channel'],r['component'])):
        relations = [dict(reference_component=r['component'],
            exact_same_carrier=owner['rf_hz']==r['rf_hz'],
            **time_relation(owner,r,grid)) for r in references]
        flags = classify(owner,owner['component'] in curved,accepted,reference_ids,relations)
        same = any(x['exact_same_carrier'] and x['relation'] in ('interval_overlap','adjacent_native_slices') for x in relations)
        rows.append(dict(**owner,**flags,reference_time_RF_relations=relations,
            same_carrier_primary_eligible=bool(flags['primary_eligible'] and same),
            same_carrier_secondary_eligible=bool(flags['secondary_noncurved_eligible'] and same),
            identity_evidence_status='metadata candidate only; no RF comparison or identity qualification'))
    counts = dict(all_complete_native_owners=len(rows),canonical_curved_owners=len(curved),
        RX2_complete_owners=sum(r['receiver']=='RX2' for r in rows),
        RX2_curved_owners=sum(r['receiver']=='RX2' and r['canonical_curved'] for r in rows),
        primary_eligible=sum(r['primary_eligible'] for r in rows),
        same_carrier_primary_eligible=sum(r['same_carrier_primary_eligible'] for r in rows),
        secondary_noncurved_eligible=sum(r['secondary_noncurved_eligible'] for r in rows),
        same_carrier_secondary_eligible=sum(r['same_carrier_secondary_eligible'] for r in rows),
        complete_original_accepted_ID_counts={a:len(accepted[a]) for a in ARMS})
    elapsed=time.monotonic()-began
    if elapsed>120:raise TimeoutError('metadata budget exceeded; no replacement')
    for b in protocol['input_bindings'].values():assert sha(b['path'])==b['sha256']
    write(HERE/'inventory.json',dict(counts=counts,rows=rows,references=references,
        original_accepted_observation_ids={a:sorted(accepted[a]) for a in ARMS},
        frozen_native_time_grid_s=grid,seconds=elapsed,
        protocol_sha256=sha(HERE/'protocol.json'),new_RF_scores=0,position_fits=0,GPS_used=False))
    with (HERE/'inventory.csv').open('x',newline='') as stream:
        fields=['component','receiver','channel','rf_hz','points','start_s','end_s','canonical_curved','primary_eligible','same_carrier_primary_eligible','secondary_noncurved_eligible','same_carrier_secondary_eligible','eligibility_reasons']
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader()
        for r in rows:writer.writerow({k:'; '.join(r[k]) if k=='eligibility_reasons' else r[k] for k in fields})
    write(HERE/'seal.json',dict(files={str(HERE/n):sha(HERE/n) for n in ('inventory.py','test_inventory.py','protocol.json','protocol_seal.json','inventory.json','inventory.csv')},RF_comparison_authorized=False))
    print(json.dumps(dict(counts=counts,seconds=elapsed),indent=2))


if __name__ == '__main__':
    main()
