"""Conditional whole-curved-source prediction; RF-only, no position fitting."""
from pathlib import Path
import json, signal, time
import numpy as np
import mechanism as m
OUT=Path(__file__).resolve().parent
CASES=['DS23-0259','DS23-0041','DS23-0272']

def estimate(rows, arm):
    r=[x for x in rows if x['arm']==arm]
    y=np.array([x['mean_error_hz'] for x in r]); v=np.array([x['shared_mean_variance_hz2']+x['noise_mean_variance_hz2'] for x in r])
    grid=np.r_[0.,np.geomspace(1,10000,1201)]
    scores=np.array([np.sum(np.log(v+s*s)+y*y/(v+s*s)) for s in grid])
    best=int(np.argmin(scores)); supported=grid[scores<=scores[best]+3.841]
    return dict(n=len(r),method_of_moments_variance_hz2=float(np.mean(y*y-v)),
        marginal_pseudolikelihood_best_sd_hz=float(grid[best]),diagnostic_delta3p841_score_band_sd_hz=[float(supported.min()),float(supported.max())],
        delta_score_by_sd={str(s):float(np.sum(np.log(v+s*s)+y*y/(v+s*s))-scores[best]) for s in [0,300,600,3000]},
        warning='Marginal pseudolikelihood: held-source fits share training observations; families are not joint-independent; interval is diagnostic only.')

def main():
    protocol=dict(cases=CASES,arms=list(m.ARMS),selection='one longest retained whole curved source per family; family must retain another curved source; top six by retained points then component key',
        max_sources=18,seconds_per_case=60,position='frozen full-parent endpoint; conditional diagnostic, not full cross validation',
        phase='up to five fixed-position phase-refresh rounds from frozen full-parent reference; held data excluded from every nuisance update',
        predictor='held source fragment constant column zeroed; all other shared features retained',
        noise='fixed-window native observation sigma times sqrt(2), independent mean variance sum(sigma^2)/n^2',
        widths_hz=[0,300,600,3000],no_GPS=True,no_new_RF=True,no_production_adoption=True)
    m.write(OUT/'protocol.json',protocol); rows=[]; inventory=[]
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('60 second case cap')))
    for case in CASES:
        signal.alarm(60); start=time.monotonic()
        d,kind,_,record=m.load(case)
        base=m.exp.paths.build(d,kind,'c0',d['arms']['c0']['phase_reference'])
        byfamily={}
        for slot,(row,i,sl) in enumerate(zip(base.rows,base.members,base.slices,strict=True)):
            n=int(base.keep[sl].sum())
            if n:byfamily.setdefault(row['candidate_index'],[]).append((slot,i,sl,n))
        eligible=[]
        for family,items in byfamily.items():
            if len(items)<2:continue
            winner=sorted(items,key=lambda v:(-v[3],d['scan'].tracks[v[1]]['key']))[0]
            eligible.append((family,*winner))
        chosen=sorted(eligible,key=lambda v:(-v[4],d['scan'].tracks[v[2]]['key']))[:6]
        inventory.append(dict(case=case,all_supported_families=len(byfamily),eligible_families=len(eligible),selected=[dict(family=int(f),source=d['scan'].tracks[i]['key'],retained=n,full_points=len(d['scan'].tracks[i]['times'])) for f,slot,i,sl,n in chosen]))
        m.write(OUT/'selection.json',inventory)
        for family,slot,i,sl,n in chosen:
            keep=np.asarray(d['keep']).copy();keep[sl]=False
            assert not keep[sl].any()
            dd=dict(d,keep=keep,entries=[])
            for arm in m.ARMS:
                saved=d['arms'][arm]; reference=np.asarray(saved['phase_reference']); history=[]
                for round_index in range(5):
                    p=m.exp.paths.build(dd,kind,arm,reference)
                    c=p.calculate(np.asarray(saved['endpoint_east_north_km']))
                    phases=np.clip(p.state(np.asarray(saved['endpoint_east_north_km']))['phases'][p.labels],-15,15)
                    phase_change=float(np.max(abs(phases-reference)));history.append(phase_change)
                    if phase_change<=.01:break
                    reference=phases
                u=c['features']; held=u[sl].copy()
                const_start=p.hardware.shape[1]+p.smooth.shape[1]+len(p.labels)+3*len(p.supported)
                held[:,const_start+slot]=0
                residual=p.values[sl]-p.q[sl]*c['intercept'][sl]-held@c['coefficient']
                g=p.noise_groups[p.keep];weights=np.asarray(d['powers'])[g]*c['noise_precision'][g]/p.point_noise[p.keep]**2
                gram=np.diag(c['coefficient_prior_precision'])+u[p.keep].T@(u[p.keep]*weights[:,None])
                mean_feature=held.mean(axis=0); shared=float(mean_feature@np.linalg.solve(gram,mean_feature))
                track=d['scan'].tracks[i];meta=d['scan'].fixed_window_noise
                sigma=np.array([meta['per_observation_noise_sigma_hz'][o] if meta['extra_parameter_BIC_gain']>0 else d['scan'].radio_sigma_hz for o in track['observation_ids']])*np.sqrt(2)
                rows.append(dict(case=case,arm=arm,family=int(d['scan'].norads[family]),source=track['key'],n=len(residual),retained_training_removed=n,
                    phase_reference_update_max_s=phase_change,phase_history_s=history,phase_converged=phase_change<=.01,mean_error_hz=float(residual.mean()),shared_mean_variance_hz2=shared,noise_mean_variance_hz2=float(np.sum(sigma*sigma)/len(sigma)**2),
                    centered_RMS_hz=float(np.sqrt(np.mean((residual-residual.mean())**2))),receiver=int(track['receiver']),channel=int(track['channel'])))
        signal.alarm(0);print(case,len(chosen),'sources',time.monotonic()-start,flush=True)
        m.write(OUT/'results.json',dict(protocol=protocol,inventory=inventory,rows=rows,estimates={a:estimate(rows,a) for a in m.ARMS}))

if __name__=='__main__':main()
