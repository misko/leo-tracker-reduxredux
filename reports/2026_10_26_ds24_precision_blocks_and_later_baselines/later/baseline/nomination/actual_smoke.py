"""Load actual terminal saved contexts without building J or ranking owners."""
import time
STARTED=time.monotonic()
import hashlib
import json
from pathlib import Path
import traceback
import numpy as np
from nominate import HERE,BASE,WORK,CASES,ARMS,context,read,sha,write


def main():
    seal=BASE/'later_RF_seal.json';rows=[];error=None
    for path,h in read(seal)['files'].items():
        if sha(path)!=h:raise ValueError('terminal baseline binding changed')
    try:
        for case in CASES:
            d=context(case);tracks={t['key']:t for t in d['scan'].tracks}
            labels=sorted({r['candidate_index'] for r in d['node']['seed']['rows']})
            expected=sum(len(tracks[r['component']]['observation_ids']) for r in d['node']['seed']['rows'])
            if len(d['keep'])!=expected or len(d['means'])!=len(labels):raise ValueError('saved native mask/mean axis differs')
            for arm in ARMS:
                a=d['arms'][arm]
                if len(a['phase_reference'])!=len(labels) or len(a['endpoint_east_north_km'])!=2:raise ValueError('arm phase/position axis differs')
                if not np.isfinite(np.r_[a['phase_reference'],a['endpoint_east_north_km']]).all():raise ValueError('nonfinite saved arm')
            predictive=[]
            for e in d['entries']:
                if e['observation_ids']!=tracks[e['component']]['observation_ids']:raise ValueError('whole predictive native join differs')
                predictive+=e['observation_ids']
            if len(predictive)!=len(set(predictive)):raise ValueError('duplicate predictive IDs')
            rows.append(dict(case=case,passed=True,curved_mask_length=len(d['keep']),active_curved_points=int(np.sum(d['keep'])),
                allocated_family_labels=len(labels),phase_reference_lengths={a:len(d['arms'][a]['phase_reference']) for a in ARMS},
                predictive_entries=len(d['entries']),predictive_IDs=len(predictive),whole_predictive_joins_exact=True,
                original_GLRT_count=len(d['observations']),saved_parent_sha256=sha(WORK/'family_cavity/position'/(case+'.json'))))
    except Exception as exc:error=dict(error=repr(exc),traceback=traceback.format_exc())
    seconds=time.monotonic()-STARTED
    preparation=read(BASE/'later_protocol.json')['preparation_seconds']+read(HERE/'protocol.json')['additional_preparation_seconds']+seconds
    write('actual_smoke.json',dict(all_passed=error is None and len(rows)==4,rows=rows,failure=error,seconds=seconds,
        cumulative_baseline_preparation_seconds=preparation,preparation_cap_pass=preparation<=60,
        baseline_RF_seal_sha256=sha(seal),nomination_protocol_sha256=sha(HERE/'protocol.json'),
        source_sha256=sha(__file__),J_or_ranking_or_score_or_optimizer_calls=0,GPS_read=False))
    if error or preparation>60:raise RuntimeError(error or 'preparation cap exhausted')
    print(json.dumps(dict(passed=True,seconds=seconds,preparation_seconds=preparation)))


if __name__=='__main__':main()
