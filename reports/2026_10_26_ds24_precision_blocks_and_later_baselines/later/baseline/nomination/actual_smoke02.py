"""Versioned four-context schema smoke; no J, owner scores or optimizers."""
import time
STARTED=time.monotonic()
import numpy as np
from nominate02 import HERE,BASE,WORK,CASES,ARMS,context,read,sha,write


def main():
    seal=BASE/'later_RF_seal.json';rows=[]
    for path,h in read(seal)['files'].items():
        if sha(path)!=h:raise ValueError('terminal baseline binding changed')
    for case in CASES:
        d=context(case);tracks={t['key']:t for t in d['scan'].tracks}
        labels=sorted({r['candidate_index'] for r in d['node']['seed']['rows']})
        expected=sum(len(tracks[r['component']]['observation_ids']) for r in d['node']['seed']['rows'])
        if len(d['keep'])!=expected or len(d['means'])!=len(labels):raise ValueError('saved native mask/mean axis differs')
        for arm in ARMS:
            a=d['arms'][arm]
            if len(a['phase_reference'])!=len(labels) or len(a['endpoint_east_north_km'])!=2:raise ValueError('saved arm axis differs')
            if not np.isfinite(np.r_[a['phase_reference'],a['endpoint_east_north_km']]).all():raise ValueError('nonfinite saved arm')
        predictive=[]
        for e in d['entries']:
            if e['observation_ids']!=tracks[e['component']]['observation_ids']:raise ValueError('whole predictive join differs')
            predictive+=e['observation_ids']
        if len(predictive)!=len(set(predictive)):raise ValueError('duplicate predictive IDs')
        rows.append(dict(case=case,passed=True,active_curved_points=int(np.sum(d['keep'])),
            allocated_family_labels=len(labels),phase_reference_lengths={a:len(d['arms'][a]['phase_reference']) for a in ARMS},
            predictive_IDs=len(predictive),whole_predictive_joins_exact=True,absolute_phase_diagnostic=d['absolute_phase_diagnostic'],
            original_GLRT_count=len(d['observations']),parent_sha256=sha(WORK/'family_cavity/position'/(case+'.json'))))
    seconds=time.monotonic()-STARTED
    prep=read(BASE/'later_protocol.json')['preparation_seconds']+read(HERE/'protocol02.json')['additional_preparation_seconds']+seconds
    write('actual_smoke02.json',dict(all_passed=len(rows)==4,rows=rows,seconds=seconds,
        cumulative_baseline_preparation_seconds=prep,preparation_cap_pass=prep<=60,
        baseline_RF_seal_sha256=sha(seal),nomination_protocol_sha256=sha(HERE/'protocol02.json'),
        source_sha256=sha(__file__),J_or_ranking_or_score_or_optimizer_calls=0,GPS_read=False))
    if prep>60:raise ValueError('preparation cap exhausted')
    print('SMOKE_PASS',seconds,prep)


if __name__=='__main__':main()
