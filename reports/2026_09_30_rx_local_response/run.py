import hashlib
import json
import math
from pathlib import Path


def calibrate(categories, background, strength=20.0):
    if strength <= 0 or not math.isfinite(strength):
        raise ValueError('positive finite strength required')
    if len(background) != 4 or any(not math.isfinite(x) or x <= 0 for x in background):
        raise ValueError('four positive background probabilities required')
    if not math.isclose(sum(background), 1.0, abs_tol=1e-10):
        raise ValueError('normalized background required')
    counts = [0]*4
    for y in categories:
        if not isinstance(y,int) or not 0 <= y <= 3:
            raise ValueError('four-state integer category required')
        counts[y] += 1
    return [(n+strength*p)/(len(categories)+strength) for n,p in zip(counts,background)]


def main():
    here=Path(__file__).resolve().parent
    source=here.parent/'2026_09_28_rx_paired_state_cv'
    records=[]; bindings={}
    for i in range(6):
        path=source/f'fold-{i}.json'; payload=path.read_bytes(); doc=json.loads(payload)
        bindings[str(path.relative_to(Path.cwd()))]=hashlib.sha256(payload).hexdigest()
        total=0.; windows=0; lanes=[]
        for lane in doc['evaluations']['P']['lanes']:
            early=[r for r in lane['windows'] if r['role']=='reception']
            later=[r for r in lane['windows'] if r['role']=='held_frequency']
            assert early and later
            assert max(r['prediction_utc_ns'] for r in early)<min(r['prediction_utc_ns'] for r in later)
            probabilities=calibrate([r['category'] for r in early],doc['background'])
            score=math.fsum(math.log(probabilities[r['category']]) for r in later)
            total+=score; windows+=len(later)
            lanes.append({'lane':lane['lane'],'early_count':len(early),'later_count':len(later),
                          'probabilities':probabilities,'later_full_score':score,
                          'calibration_window_ids':[r['source_window_id'] for r in early],
                          'later_window_ids':[r['source_window_id'] for r in later]})
        baselines={}
        for arm in ('P','U','O'):
            rows=[r for l in doc['evaluations'][arm]['lanes'] for r in l['windows'] if r['role']=='held_frequency']
            saved=doc['evaluations'][arm]['roles']['held_frequency']
            assert len(rows)==windows==saved['windows']
            full=math.fsum(r['full_log_score'] for r in rows)
            assert abs(full-saved['full_log_score'])<1e-8
            baselines[arm]=full/windows
        baselines['background']=doc['evaluations']['P']['roles']['held_frequency']['reference_log_score']/windows
        records.append({'session':doc['held_session'],'windows':windows,'lanes':lanes,
                        'local_score_per_window':total/windows,'baselines':baselines,
                        'gains':{k:total/windows-v for k,v in baselines.items()}})
    summary={k:{'mean_gain':math.fsum(r['gains'][k] for r in records)/6,
                'positive_records':sum(r['gains'][k]>1e-6 for r in records)}
             for k in records[0]['gains']}
    result={'records':records,'summary':summary,'source_sha256':bindings,'strength':20.0}
    with (here/'results.json').open('x') as f: json.dump(result,f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__': main()
