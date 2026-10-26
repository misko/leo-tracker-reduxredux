"""Approved deterministic RF-only coherent block nomination, no forecasts."""
from collections import defaultdict


def lanes(ledger,curved_ids):
    groups=defaultdict(list)
    for row in ledger['staged']:
        if row['status']!='new_native_exploratory_addition'or row['existing_owner']:continue
        if 5<=row['channel']<=8:groups[row['channel'],row['native_receiver_id']].append(row)
    eligible=[]
    for (channel,rx),rows in groups.items():
        curved=[r for r in rows if r['target_observation_id']in curved_ids]
        if not curved:continue
        seed=min(curved,key=lambda r:((r['native']['start_counter']+r['native']['stop_counter'])/2,r['target_observation_id']))
        eligible.append(dict(case=ledger['case'],channel=channel,nominating_receiver_id=rx,
            new_curved_count=len(curved),new_native_count=len(rows),edge=seed['native']['edge'],
            seed_observation_id=seed['target_observation_id'],seed_native=seed['native']))
    eligible.sort(key=lambda r:(-r['new_curved_count'],-r['new_native_count'],r['channel'],r['nominating_receiver_id']))
    return [dict(row,lane_rank=i+1)for i,row in enumerate(eligible)]


def nominate(block,probes,rate,window_samples=200000):
    native=block['seed_native'];center=(native['start_counter']+native['stop_counter'])/2
    original_start=min(p['valid_start_counter']for p in probes)
    original_stop=max(p['valid_start_counter']for p in probes)+window_samples
    start=max(original_start,center-12*rate);stop=min(original_stop,center+12*rate)
    by_visit={}
    for p in probes:
        if p['channel']!=block['channel']or p['edge']!=block['edge']:continue
        if not start<=p['valid_start_counter']+window_samples/2<=stop:continue
        current=by_visit.get(p['visit_index'])
        if current is not None and current['valid_start_counter']!=p['valid_start_counter']:
            raise ValueError('paired native origins disagree')
        if current is None or p['receiver_id']<current['receiver_id']:
            by_visit[p['visit_index']]={k:v for k,v in p.items()if k!='candidates'}
    ordered=sorted(by_visit.values(),key=lambda p:(p['valid_start_counter'],p['visit_index']))
    return dict(block,block_id=f"{block['case']}-L{block['lane_rank']}-CH{block['channel']}-RX{block['nominating_receiver_id']}",
        center_counter=center,requested_interval_closed=[center-12*rate,center+12*rate],
        clipped_interval_closed=[start,stop],recording_processed_extent=[original_start,original_stop],
        enumerated_paired_visits=len(ordered),retained_paired_visits=min(len(ordered),80),
        capped=len(ordered)>80,probes=ordered[:80])


def deduplicate(blocks):
    pairs={}
    for block in blocks:
        for probe in block['probes']:
            key=(block['case'],probe['visit_index'])
            if key not in pairs:pairs[key]=dict(case=block['case'],probe=probe,block_ids=[])
            if pairs[key]['probe']!=probe:raise ValueError('overlap metadata disagreement')
            pairs[key]['block_ids'].append(block['block_id'])
    if len(blocks)>4 or len(pairs)>320:raise ValueError('approved block/window cap exceeded')
    return sorted(pairs.values(),key=lambda r:(r['case'],r['probe']['valid_start_counter'],r['probe']['visit_index']))
