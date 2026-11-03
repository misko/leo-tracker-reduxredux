"""Descriptive family2 census of epoch-linked detections omitted by tracking.

Use the frozen donor16 threshold on both preselected family2 DS11 pilot records.
Count unique raw candidates, not track copies. This is not satellite identity
verification and cannot distinguish accidental timing coincidences by itself.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
from epoch_pairs import delta_us

HERE=Path(__file__).resolve().parent


def census(doc,threshold):
    retained={cid for track in doc['tracks'] for cid in track['candidate_ids']}
    counts=Counter();windows=Counter()
    for opportunity in doc['opportunities']:
        seen=set()
        fs=opportunity['source_window']['sample_rate_hz']
        for rx in (0,1):
            aview=opportunity['receivers'][f'rx{rx}']['candidates']
            bview=opportunity['receivers'][f'rx{1-rx}']['candidates']
            for a in aview:
                if a['projected_candidate_id'] not in retained:continue
                partners=[b for b in bview if b['passed_fractional_margin_gate'] and abs(delta_us(a,b,fs,750.))<=threshold]
                if not partners:state='no_timing_partner'
                elif any(b['projected_candidate_id'] in retained for b in partners):state='retained_timing_partner'
                else:state='raw_only_timing_partner'
                counts[state]+=1;seen.add(state)
        windows.update(seen)
    return dict(unique_retained_candidate_counts=dict(counts),window_counts=dict(windows))


def main():
    calpath=HERE/'soft-calibration.json';cal=json.loads(calpath.read_text())
    paths=[HERE.parent/'acquisition_position'/f'input-{c}-{i:02d}.json' for c,i in (('original',0),('additional',1))]
    rows=[]
    for path in paths:
        doc=json.loads(path.read_text());assert doc['family']==2
        rows.append(dict(cohort=doc['cohort'],index=doc['index'],**census(doc,cal['threshold_us'])))
    result=dict(rows=rows,threshold_us=cal['threshold_us'],scope='family2 descriptive raw-detection census, no position fitting or identity verification',sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths+[calpath,Path(__file__),HERE/'epoch_pairs.py']})
    with (HERE/'raw-partner-audit.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
