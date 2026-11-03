import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent/'2026_09_29_waveform_chirp'
sys.path.insert(0,str(PARENT))
from chirp import fit, error

STRENGTHS = [0., .25, .5, .75, 1.]


def choose(rows, target):
    donors=[r for r in rows if r['phase']=='calibration' and r['dataset']!=target]
    datasets=sorted({r['dataset'] for r in donors})
    if len(datasets)!=2:
        raise ValueError('Require both donor datasets')
    curve=[]
    for index in range(len(STRENGTHS)):
        ds_scores=[]
        for ds in datasets:
            visits=sorted({r['signal'] for r in donors if r['dataset']==ds})
            ds_scores.append(np.mean([np.mean([r['errors'][index] for r in donors if r['dataset']==ds and r['signal']==visit]) for visit in visits]))
        curve.append(float(np.mean(ds_scores)))
    index=int(np.argmin(curve))
    return dict(strength=STRENGTHS[index],index=index,donor_datasets=datasets,calibration_nmse=curve)


def main():
    source=PARENT/'results.json'
    prior=json.loads(source.read_text())
    for path,digest in prior['hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    hashes=dict(prior['hashes'])
    hashes[str(source)]=hashlib.sha256(source.read_bytes()).hexdigest()
    groups={(r['dataset'],r['signal'],r['receiver']) for r in prior['rows']}
    old={(r['signal'],r['receiver'],r['first_frame']):r for r in prior['rows']}
    rows, fits=[],[]
    for ds,name,rx in sorted(groups):
        path=HERE.parent/f'2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz'
        with np.load(path) as archive:
            values=archive[f'rx{rx}'].copy()
        for first in range(0,80,10):
            phase='calibration' if first<30 else 'evaluation'
            block=values[first:first+10]
            fitted=fit(block)
            fits.append(dict(dataset=ds,signal=name,receiver=rx,first_frame=first,phase=phase,fit=fitted))
            for frame in [8,9]:
                errors=[]
                for strength in STRENGTHS:
                    a=strength if fitted['qualified'] else 0.
                    f=fitted['constant_hz']+a*(fitted['linear_hz']-fitted['constant_hz'])
                    errors.append(error(block[frame],frame,f,a*fitted['rate_hz_s']))
                if phase=='evaluation':
                    previous=old[name,rx,first]['evaluations'][frame-8]
                    assert abs(errors[0]-previous['constant_nmse'])<1e-10
                    assert abs(errors[-1]-previous['linear_nmse'])<1e-10
                rows.append(dict(dataset=ds,signal=name,receiver=rx,frame=first+frame,phase=phase,errors=errors))
    selections={ds:choose(rows,ds) for ds in ['DS7','DS8','DS9']}
    summary=[]
    for ds,selection in selections.items():
        subset=[r for r in rows if r['dataset']==ds and r['phase']=='evaluation']
        gains=[r['errors'][0]-r['errors'][selection['index']] for r in subset]
        summary.append(dict(dataset=ds,n=len(subset),selection=selection,
                            improved=sum(g>1e-10 for g in gains),worsened=sum(g< -1e-10 for g in gains),
                            unchanged=sum(abs(g)<=1e-10 for g in gains),mean_gain=float(np.mean(gains)),
                            constant_nmse=float(np.mean([r['errors'][0] for r in subset])),
                            selected_nmse=float(np.mean([r['errors'][selection['index']] for r in subset]))))
    for name in ['run.py','test_transfer.py','PROTOCOL.md']:
        p=HERE/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    result=dict(strengths=STRENGTHS,rows=rows,fits=fits,summary=summary,hashes=hashes)
    with (HERE/'results.json').open('x') as out:
        json.dump(result,out,indent=2,allow_nan=False)
    print(json.dumps(summary,indent=2))
    print('Fits',len(fits),'qualified',sum(r['fit']['qualified'] for r in fits))


if __name__=='__main__':
    main()
