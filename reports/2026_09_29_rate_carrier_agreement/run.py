import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_29_waveform_chirp'))
from chirp import fit, error


def agreement(first,second):
    if not first['qualified'] or not second['qualified']:
        return 0.
    r=np.array([first['rate_hz_s'],second['rate_hz_s']],dtype=float)
    if not np.all(np.isfinite(r)):
        raise ValueError('Nonfinite rate')
    scale=max(abs(r))
    if scale==0:
        return 0.
    r=r/scale
    return float(max(0.,2*r[0]*r[1]/np.sum(r*r)))


def main():
    source=HERE.parent/'2026_09_29_rate_transfer/results.json'
    parent=json.loads(source.read_text())
    for path,digest in parent['hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    hashes=dict(parent['hashes']);hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    strengths={s['dataset']:s['selection']['strength'] for s in parent['summary']}
    old={(r['signal'],r['receiver'],r['frame']):r for r in parent['rows'] if r['phase']=='evaluation'}
    rows=[]
    for block in parent['fits']:
        if block['phase']!='evaluation':
            continue
        name,rx,first=block['signal'],block['receiver'],block['first_frame']
        path=HERE.parent/f'2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz'
        with np.load(path) as archive:
            values=archive[f'rx{rx}'][first:first+10]
        assert values.shape==(10,300,8)
        subsets=[fit(values[:,:,offset::2]) for offset in [0,1]]
        weight=agreement(*subsets)
        strength=strengths[block['dataset']]
        full=block['fit']
        evaluations=[]
        for frame in [8,9]:
            scores={}
            for label,a in [('constant',0.),('reduced',strength),('agreement',strength*weight)]:
                if not full['qualified']:
                    a=0.
                f=full['constant_hz']+a*(full['linear_hz']-full['constant_hz'])
                scores[label]=error(values[frame],frame,f,a*full['rate_hz_s'])
            previous=old[name,rx,first+frame]
            assert abs(scores['constant']-previous['errors'][0])<1e-10
            assert abs(scores['reduced']-previous['errors'][parent['strengths'].index(strength)])<1e-10
            evaluations.append(dict(frame=first+frame,nmse=scores,
                                    gain_vs_constant=scores['constant']-scores['agreement'],
                                    gain_vs_reduced=scores['reduced']-scores['agreement']))
        rows.append(dict(dataset=block['dataset'],signal=name,receiver=rx,first_frame=first,
                         subset_fits=subsets,agreement=weight,strength=strength,
                         applied_strength=strength*weight,evaluations=evaluations))
    summary=[]
    for ds in ['DS7','DS8','DS9']:
        subset=[r for r in rows if r['dataset']==ds]
        e=[e for r in subset for e in r['evaluations']]
        summary.append(dict(dataset=ds,n=len(e),zero_agreement=sum(r['agreement']==0 for r in subset),
                            median_agreement=float(np.median([r['agreement'] for r in subset])),
                            mean_gain_vs_constant=float(np.mean([x['gain_vs_constant'] for x in e])),
                            mean_gain_vs_reduced=float(np.mean([x['gain_vs_reduced'] for x in e])),
                            improved=sum(x['gain_vs_constant']>1e-10 for x in e),
                            worsened=sum(x['gain_vs_constant']< -1e-10 for x in e),
                            unchanged=sum(abs(x['gain_vs_constant'])<=1e-10 for x in e)))
    for name in ['run.py','test_agreement.py','PROTOCOL.md']:
        p=HERE/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'results.json').open('x') as out:
        json.dump(dict(rows=rows,summary=summary,hashes=hashes),out,indent=2,allow_nan=False)
    print(json.dumps(summary,indent=2))
    print('Qualified subset fits',sum(f['qualified'] for r in rows for f in r['subset_fits']))


if __name__=='__main__':
    main()
