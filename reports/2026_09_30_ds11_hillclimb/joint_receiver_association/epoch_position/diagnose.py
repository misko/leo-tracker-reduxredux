"""Audit timing conflicts and exact assignment marginals at the sealed fits."""
import json
from pathlib import Path
import sys
import time
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'acquisition_position'))
sys.path.insert(0,str(HERE.parent/'posterior_diagnostic'))
from common import base,read,digest,verify_sources
from fit import load
from probes import probe
import model as timing_model


def main(cohort,index):
    started=time.monotonic()
    old,initial,sources=load(cohort,index,'doppler')
    bound=read(HERE.parent/'acquisition_position'/f'input-{cohort}-{index:02d}.json')
    calpath=HERE.parent/'detection_evidence/soft-calibration.json'
    reference_path=HERE.parent/'posterior_diagnostic'/f'diagnostic-{cohort}-{index:02d}.json'
    reference_doc=read(reference_path)
    verify_sources(reference_doc)
    reference=reference_doc['reference']
    outputs={}
    for arm,strength in [('doppler',0.),('timing',1.)]:
        fitpath=HERE/f'fit-{cohort}-{index:02d}-{arm}.json'
        fit=read(fitpath)
        verify_sources(fit)
        sources[str(fitpath)]=digest(fitpath)
        model=timing_model.build(old.geometry.document,read(base(cohort)/'plan.json')['config'],bound,read(calpath),strength)
        contexts=[]
        for lane in model.lanes:
            tids=sorted(lane['left']+lane['right'])
            candidates=sorted({c for tid in tids for c in model.meta[tid]['candidate_norad']})
            contexts.extend((tids,candidates) for branch in lane['ownership_alternatives'])
        captured=[]
        def capture(n,factors):
            tids,candidates=contexts[len(captured)]
            score,gradient,diagnostic=probe(n,factors,candidates,[reference[t]['norad'] for t in tids])
            captured.append(diagnostic)
            return score,gradient
        ordinary=model.evaluate(fit['x'],gradient=False)
        original_partition=timing_model.partition
        timing_model.partition=capture
        try:
            value=model.evaluate(fit['x'],gradient=False)
        finally:
            timing_model.partition=original_partition
        assert abs(value['score']-ordinary['score'])<1e-8
        probabilities={}
        offset=0
        edges=[]
        for lane,lane_result in zip(model.lanes,value['lanes'],strict=True):
            n=len(lane['ownership_alternatives'])
            weights=np.array(lane_result['ownership_posterior'])
            p=weights@np.stack([c['reference_probability'] for c in captured[offset:offset+n]])
            tids=contexts[offset][0]
            probabilities.update({t:float(v) for t,v in zip(tids,p,strict=True)})
            matrix=sum(w*m for w,m in zip(weights,model.timing_matrices[False][offset:offset+n],strict=True))
            for i,j in zip(*np.nonzero(matrix)):
                same=reference[tids[i]]['norad']==reference[tids[j]]['norad']
                edges.append(dict(left=tids[i],right=tids[j],coefficient=float(matrix[i,j]),original_same=same,conflict=bool((matrix[i,j]>0)!=same),minimum_original_confidence=min(reference[tids[i]]['original_probability'],reference[tids[j]]['original_probability'])))
            offset+=n
        outputs[arm]=dict(reference_probability=probabilities,lost_majority=sum(p<.5 for p in probabilities.values()),expected_changed=sum(1-p for p in probabilities.values()),edges=edges,score=value['score'])
    delta=max(abs(p-outputs['doppler']['reference_probability'][t]) for t,p in outputs['timing']['reference_probability'].items())
    sources.update({str(p):digest(p) for p in (Path(__file__),calpath,reference_path,HERE.parent/'posterior_diagnostic/probes.py')})
    result=dict(cohort=cohort,index=index,arms=outputs,max_reference_probability_change=delta,sources=sources,elapsed_s=time.monotonic()-started)
    with (HERE/f'diagnostic-{cohort}-{index:02d}.json').open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(cohort=cohort,index=index,max_reference_probability_change=delta,arms={a:dict(lost_majority=o['lost_majority'],expected_changed=o['expected_changed'],edges=len(o['edges']),conflicts=sum(e['conflict'] for e in o['edges'])) for a,o in outputs.items()})))


if __name__=='__main__':
    main(sys.argv[1],int(sys.argv[2]))
