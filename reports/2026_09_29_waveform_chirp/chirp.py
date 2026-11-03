import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize, minimize_scalar

TS = 4.4e-6
TRAIN = np.arange(20,220)
CAL = np.arange(20,120)
HELD = np.arange(220,300)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def basis(frames, symbols):
    # Zero is the midpoint of the eight fitting frame slots. Static phase
    # offsets from omitted symbol-origin constants are absorbed by each gain.
    u = (np.asarray(frames)[:,None]-3.5)/750 + np.asarray(symbols)[None,:]*TS
    return np.stack([u, .5*u*u],axis=-1)


def objective(p, values, b, coarse):
    physical = np.array([coarse,0.])+p*np.array([1000.,100000.])
    z = values*np.exp(-2j*np.pi*(b@physical))[:,:,None]
    g = z.mean(axis=1)
    dg = np.mean(z[:,:,:,None]*(-2j*np.pi*b*np.array([1000.,100000.]))[:,:,None,:],axis=1)
    energy = np.sum(abs(values)**2)/values.shape[1]
    return -float(np.sum(abs(g)**2)/energy), -2*np.real(np.sum(g.conj()[:,:,None]*dg,axis=(0,1)))/energy


def fit(values):
    y=values[:8,TRAIN]
    spec=np.sum(abs(np.fft.fft(y,n=8192,axis=1))**2,axis=(0,2))
    coarse=np.fft.fftfreq(8192,TS)[np.argmax(spec)]
    spacing=1/(8192*TS)
    b=basis(np.arange(8),TRAIN)
    constant=minimize_scalar(lambda f: objective(np.zeros(2),y,b,f)[0],bounds=(coarse-spacing,coarse+spacing),method='bounded')
    assert constant.success
    f=float(constant.x)
    result=minimize(objective,np.zeros(2),args=(y,b,f),jac=True,method='L-BFGS-B',
                    bounds=[(-1.5,1.5),(-1.,1.)],options=dict(maxiter=300,ftol=1e-14,gtol=1e-8))
    qualified=bool(result.success and max(abs(result.jac))<1e-5 and abs(result.x[0])<1.499 and abs(result.x[1])<.999)
    return dict(constant_hz=f,linear_hz=f+float(result.x[0])*1000,
                rate_hz_s=float(result.x[1])*100000,qualified=qualified,
                success=bool(result.success),gradient=result.jac.tolist(),message=str(result.message))


def error(values, frame, f, rate):
    p=np.array([f,rate])
    gain=np.mean(values[CAL]*np.exp(-2j*np.pi*(basis([frame],CAL)[0]@p))[:,None],axis=0)
    pred=gain*np.exp(2j*np.pi*(basis([frame],HELD)[0]@p))[:,None]
    return float(np.sum(abs(values[HELD]-pred)**2)/np.sum(abs(values[HELD])**2))


def main():
    source=ROOT/'reports/2026_09_29_block_frequency_support/results.json'
    parent=json.loads(source.read_text())
    hashes={str(source):hashlib.sha256(source.read_bytes()).hexdigest()}
    for path,digest in parent['input_sha256'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    rows=[]
    for old in parent['blocks']:
        name,rx,first=old['signal'],old['receiver'],old['first_frame']
        path=ROOT/f'reports/2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz'
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert hashes[str(path)]==parent['input_sha256'][str(path)]
        with np.load(path) as archive:
            values=archive[f'rx{rx}'][first:first+10]
        fitted=fit(values)
        f,rate=(fitted['linear_hz'],fitted['rate_hz_s']) if fitted['qualified'] else (fitted['constant_hz'],0.)
        evaluations=[]
        for frame in [8,9]:
            c=error(values[frame],frame,fitted['constant_hz'],0.)
            l=error(values[frame],frame,f,rate)
            evaluations.append(dict(frame=first+frame,constant_nmse=c,linear_nmse=l,gain=c-l))
        rows.append(dict(dataset=old['dataset'],signal=name,receiver=rx,first_frame=first,fit=fitted,evaluations=evaluations))
    summary=[]
    for name in dict.fromkeys(r['signal'] for r in rows):
        subset=[r for r in rows if r['signal']==name]
        gains=[e['gain'] for r in subset for e in r['evaluations']]
        summary.append(dict(signal=name,qualified=sum(r['fit']['qualified'] for r in subset),
                            improved=sum(g>0 for g in gains),mean_gain=float(np.mean(gains)),median_gain=float(np.median(gains))))
    for name in ['chirp.py','PROTOCOL.md','test_chirp.py']:
        p=HERE/name;hashes[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
    with (HERE/'results.json').open('x') as out:
        json.dump(dict(rows=rows,summary=summary,hashes=hashes),out,indent=2,allow_nan=False)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
