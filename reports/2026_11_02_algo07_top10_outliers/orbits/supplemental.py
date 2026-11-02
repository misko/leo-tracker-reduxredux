"""Posthoc RF ablation motivated controls, separate from original top-two targets."""
import argparse,hashlib,time
import numpy as np
from investigate import *
from finish import enrich,paired_swaps,family,render_graph,report,old_render

def supplemental(case,n):
    setup();began=time.monotonic();d,z,replay=engine.load_case(case);base=ROOT/case;out=base/f'supplemental-{n}';out.mkdir(parents=True,exist_ok=True);ledger=read(base/'tle-ledger.json');options=[]
    for i,tr in enumerate(d['scan'].tracks):
        ix=np.array([k for k,o in enumerate(tr['observation_ids']) if z['baseline_owners']['fitted_c'].get(o)==n])
        if len(ix):options.append((float(np.ptp(tr['times'][ix])),len(ix),i,ix))
    if not options:raise ValueError('No published native owners for supplemental family')
    _,_,i,ix=max(options,key=lambda r:r[:2]);tr=d['scan'].tracks[i];t=np.asarray(tr['times'])[ix];ys={};phases={};positions={a:x for a,(p,x) in d['problems'].items()}
    for a,(p,x) in d['problems'].items():
        state=p.state(x);cal=d['scan'].hardware(tr,state['beta'])+tr['rf_hz']/11.5e9*d['scan'].rx_basis[i]@state['smooth'][tr['receiver']-1];ys[a]=(tr['values']-cal)[ix];phases[a]=float(state['phases'][list(d['scan'].norads).index(n)]) if n in d['scan'].norads else 0.
    target=dict(index=0,meta=dict(track_index=i,indices=ix,role='posthoc_ablation_influential_family',assigned_norad=n),key=tr['key'],receiver=tr['receiver'],channel=tr['channel'],rf_hz=tr['rf_hz'],times_s=t,raw_unwrapped_hz=np.asarray(tr['values'])[ix],corrected_hz=ys,observation_ids=[tr['observation_ids'][k] for k in ix],pieces=tr['pieces'],polynomial=legacy.polynomial(t,np.asarray(tr['values'])[ix]),phase0=phases,results=[])
    write(out/'run_manifest.json',dict(case=case,norad=n,posthoc=True,nomination='Completed matched family-omission ablation showed a large gate-qualified position shift. This supplemental target was not part of initial top2 nomination; removal is not recommended from influence alone.',replay=replay,ledger_path=str(base/'tle-ledger.json'),ledger_sha256=hashlib.sha256((base/'tle-ledger.json').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),positions=positions,scope='Same matched c-arm full-catalogue diagnostic and whole-family restricted model as initial study; no production ownership changes'))
    for regime in ('causal','later'):
        nums,bank,failed=legacy.bank_for(ledger[regime],z['scan_receipt']['origin_utc_ns']);rows,cov=fit_matched(t,ys,target['rf_hz']/11.5e9,nums,bank,positions,n,phases);target['results'] += [dict(r,regime=regime) for r in rows];write(out/'targets.json',[target]);write(out/f'{regime}-search-coverage.json',dict(catalogue_count=len(nums),failed_propagation=failed,models=cov));del bank;print(case,n,regime,round(time.monotonic()-began,1),flush=True)
    enrich(d,[target]);swaps=paired_swaps(d,z,[target],ledger);write(out/'targets.json',[target]);write(out/'frozen_tle_swap.json',swaps);old_render.target_figures(case,out);render_graph(target,out);families=family(d,z,[target],ledger,out);report(case,out,[target],families,swaps)
    path=out/'report.md';path.write_text(path.read_text().replace('The catalogue search compares','This is a **posthoc supplemental target**, nominated after the completed family-omission ablation, separate from the initial top-two protocol. A gate-qualified omission shift is influence evidence and does not justify removing the family.\n\nThe catalogue search compares',1));manifest=read(out/'run_manifest.json');manifest.update(status='complete',seconds=time.monotonic()-began);write(out/'run_manifest.json',manifest);print(case,n,'complete',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('case');ap.add_argument('norad',type=int);args=ap.parse_args();supplemental(args.case,args.norad)
