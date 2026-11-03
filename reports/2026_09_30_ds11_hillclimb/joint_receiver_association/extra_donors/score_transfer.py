"""Separate-record scoring of frozen family0/1 receiver coefficients."""
import json
from pathlib import Path
import sys
import numpy as np
from context import digest,read

HERE=Path(__file__).resolve().parent;PARENT=HERE.parent
sys.path.insert(0,str(PARENT));sys.path.insert(0,str(PARENT/'acquisition_calibration'))
from conditional_fit import dataset
from conditional_receiver import design,score_gradient
from fit_family import screen


def main():
    paths=[Path(__file__),HERE/'TRANSFER_PROTOCOL.md',PARENT/'conditional_fit.py',PARENT/'conditional_receiver.py',PARENT/'acquisition_calibration/fit_family.py']
    sources={str(p):digest(p) for p in paths};recordings=[]
    for i in range(4):
        path=HERE/f'donor-{i:02d}.json';doc=read(path)
        receipt=HERE/f'donor-{i:02d}.receipt.json';rp=read(receipt);assert rp['exit_code']==0
        for bound in (doc,rp):
            for p,h in bound['sources'].items():assert digest(p)==h,p
        fp=PARENT/f"acquisition_calibration/fit-{doc['family']}.json";frozen=read(fp)
        for p,h in frozen['sources'].items():assert digest(p)==h,p
        assert doc['rf_hz']==frozen['frequencies'] and doc['sample_rate_hz']==frozen['sample_rate_hz']
        frequencies=frozen['frequencies'];d=dataset(doc,frequencies)
        validation={}
        for arm in ('receiver','elevation','signed'):
            fitted=frozen['arms'][arm]['selected'];assert fitted['qualified']
            values=score_gradient(np.array(fitted['parameters']),design(d['los'],d['rf'],4,arm),d['states'])[0]
            mask=~d['train']
            validation[arm]=dict(score=float(values[mask].sum()),count=int(mask.sum()),
                                 per_source={str(int(s)):float(values[mask & (d['source']==s)].sum()) for s in np.unique(d['source'][mask])})
        controls={};p=np.array(frozen['arms']['signed']['selected']['parameters'])
        for arm in ('swapped','permuted'):
            altered=dataset(doc,frequencies,permutation=arm=='permuted')
            scores=score_gradient(p,design(altered['los'],altered['rf'],4,'swapped' if arm=='swapped' else 'signed'),altered['states'])[0]
            controls[arm]=float(scores[~altered['train']].sum())
        gate=screen(validation,controls,True)
        recordings.append(dict(ordinal=i,family=doc['family'],session_id=doc['session_id'],source_groups=len(doc['lanes']),
                               selected_tracks=len(doc['selected_tracks']),excluded_tracks=len(doc['excluded_tracks']),
                               original_bank_replay_maximum=doc['original_bank_replay_maximum'],validation=validation,controls=controls,screen=gate))
        sources.update({str(p):digest(p) for p in (path,receipt,fp)})
    families={str(f):dict(recordings=[r['ordinal'] for r in recordings if r['family']==f],
                          passed=all(r['screen']['passed'] for r in recordings if r['family']==f)) for f in (0,1)}
    out=dict(recordings=recordings,families=families,receiver_coefficients_refitted=False,
             validation_chronologically_after_calibration=False,causal_position_improvement_established=False,sources=sources)
    with (HERE/'transfer-summary.json').open('x') as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(dict(families=families,recordings=[dict(ordinal=r['ordinal'],family=r['family'],screen=r['screen'],scores={a:v['score'] for a,v in r['validation'].items()},controls=r['controls']) for r in recordings]),indent=2))


if __name__=='__main__':main()
