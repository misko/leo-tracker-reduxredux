"""Extract archived identity checks; no new likelihood evaluation or fit."""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path('/srv/bulk/leo/research/algo04-ordinary-full-ds23-20261023/raw/DS23-0259')


def main():
    discovery = json.loads((RAW/'native/DS23-0259_discovery.json').read_text())
    result = json.loads((RAW/'result.json').read_text())
    tracks = result['ordinary_graph']['arms']['c0']['gates']['tracks']
    families = sorted({(t['candidate_index'], t['norad']) for t in tracks})
    assert len(families) == discovery['active_families']
    selected = {f['key'] for f in discovery['methods']['persistent5s']['selected']}
    rows = []
    for path in discovery['methods']['persistent5s']['paths']:
        f = path['fragment']
        if f['norad'] not in (65340, 67618):
            continue
        checks = {}
        for arm, check in path['checks'].items():
            probabilities = check['probabilities']
            win = check['best_local_index']+1
            alternatives = [dict(kind='clutter' if i == 0 else 'active_family',
                                 candidate_index=None if i == 0 else families[i-1][0],
                                 norad=None if i == 0 else families[i-1][1],
                                 probability=p) for i, p in enumerate(probabilities) if i != win]
            competitor = max(alternatives, key=lambda a: a['probability'])
            checks[arm] = dict(check, alternatives=alternatives,
                               largest_archived_alternative=competitor,
                               log_odds_vs_largest_archived_alternative=math.log(probabilities[win])-math.log(competitor['probability']) if competitor['probability'] else None,
                               alternative_scores_not_archived=True,
                               zero_probability_may_be_underflow=True)
        rows.append(dict(key=f['key'], norad=f['norad'], candidate_index=f['candidate_index'],
                         receiver=f['receiver'], channel=f['channel'], rf_hz=f['rf_hz'],
                         points=len(f['times']), start_s=min(f['times']), end_s=max(f['times']),
                         times_s=f['times'], observation_ids=f['observation_ids'],
                         passed=path['passed'], selected=f['key'] in selected, checks=checks))
    output = dict(case='DS23-0259', source=str(RAW),
                  candidate_universe='currently active curved families only; not full causal catalogue',
                  active_families=[dict(candidate_index=i, norad=n) for i,n in families],
                  identity_is_conditional_not_independent_confirmation=True,
                  paths=rows)
    inv = HERE/'track_inventory0259.json'
    if inv.exists():
        physical = json.loads(inv.read_text())
        physical = physical.get('tracks', physical) if isinstance(physical, dict) else physical
        by_key = {t['key']:t for t in physical}
        for row in rows:
            supporting=[]
            for track in tracks:
                t=by_key[track['component']]
                retained = set(track['observation_ids'])
                overlap=[(oid, time) for oid, time in zip(t['observation_ids'], t['times'], strict=True)
                         if oid in retained and row['start_s'] <= time <= row['end_s']]
                if overlap:
                    supporting.append(dict(component=track['component'], norad=track['norad'],
                                           candidate_index=track['candidate_index'],receiver=t['receiver'],
                                           channel=t['channel'], points_in_interval=len(overlap),
                                           observation_ids=[oid for oid, time in overlap],
                                           times_s=[time for oid, time in overlap],
                                           compatible=track['compatible'],
                                           same_family=track['norad']==row['norad'],
                                           other_receiver=t['receiver']!=row['receiver']))
            row['curved_support_in_interval']=supporting
    else:
        output['interval_support_unavailable_without_track_times']=True
    (HERE/'identity0259.json').write_text(json.dumps(output, indent=2)+'\n')
    return output


if __name__ == '__main__':
    main()
