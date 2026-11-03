"""Shared development-only candidate/timing bank for all three decoders."""
import argparse,json,sys
import numpy as np
from benchmark import ROOT,OLD,digest
from feasible_tracklets import compile_proposals,evaluate_mode


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',choices=['A','B'],required=True);label=parser.parse_args().scan
    a=np.load(ROOT/'frozen'/f'{label}-observations.npz')
    source=ROOT/'development-expanded'/f'{label}-proposals.json';proposals=json.loads(source.read_text())['proposals']
    feasible=json.loads((ROOT/'development-tracklets'/f'{label}-feasible.json').read_text())
    pdet=.8/(13 if label=='A' else 15)
    modes=compile_proposals(proposals,a['group'],pdet);empty=np.zeros(len(a['group']),bool)
    selected={int(n):int(pi) for n,pi in feasible['selected_modes'].items()}
    for number in sorted({m['number'] for m in modes}-set(selected)):
        options=[evaluate_mode(m,empty,a['group'],a['times_s']) for m in modes if m['number']==number]
        selected[number]=max(options,key=lambda x:x['score'])['proposal']
    numbers=np.array(sorted(selected));chosen=[proposals[selected[int(n)]] for n in numbers]
    sys.path.insert(0,str(OLD))
    from exhaustive_subset import Case,circular_residual
    c=Case(label);old_source=OLD/'exhaustive-subset'/f'{label}-receipt.json'
    fit=json.loads(old_source.read_text())['arms']['fitted-c']['fit']
    params=np.array(fit['parameters']);coeff=np.array(fit['rf_coefficient_hz_per_ghz'])
    indices=np.array([p['satellite_index'] for p in chosen]);params[6+indices]=[p['total_timing_s'] for p in chosen]
    pred,visible=c.predict(indices,params,coeff)
    residual=circular_residual(c.data.measured[:,None],pred,c.prepared.alias_hz)
    allowed=np.zeros(residual.shape,bool)
    for col,p in enumerate(chosen):
        for s in p['segments']:allowed[s['eligible_rows'],col]=True
    gain=np.log(pdet/(1-pdet))-np.log(200*np.sqrt(2*np.pi))-.5*(residual/200)**2-np.log(2/c.prepared.alias_hz)
    gain[~allowed|~visible|(np.abs(residual)>600)]=-np.inf
    reps=a['canonical_rows'];out=ROOT/'development-comparison';out.mkdir(exist_ok=True)
    np.savez_compressed(out/f'{label}-inputs.npz',numbers=numbers,rows=reps,times=a['times_s'][reps],
        groups=a['group'][reps],receiver=a['receiver'][reps],channel=a['channel'][reps],rf=a['rf_hz'][reps],
        gain=gain[reps],residual=residual[reps],visible=visible[reps],parameters=params,coefficient=coeff,pdet=pdet)
    (out/f'{label}-inputs.json').write_text(json.dumps(dict(scope=__doc__,candidate_count=len(numbers),
        provenance={str(source):digest(source),str(old_source):digest(old_source)},
        mode_policy='Common preprocessing: mode-consistent feasible selector modes where selected; otherwise best independent local mode. All coherent candidate identities retained. Full-data calibration; NOT held out.',
        proposals=chosen),indent=2))
    print(label,'shared candidates',len(numbers),'finite edges',np.isfinite(gain[reps]).sum(),flush=True)


if __name__=='__main__':main()
