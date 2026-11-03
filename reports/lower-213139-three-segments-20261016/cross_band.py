"""Test whether the simultaneous late CH4 and CH5 curves share a satellite."""
import json
import numpy as np
from search import ROOT,observations,offset_fit
from shape_controls import link_segments,extend_continuity
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular,ALIAS_HZ


def normalized_difference(t4,y4,rf4,t5,y5,rf5):
    """Empirical shape comparison, before considering any satellite identity."""
    center=float(t4.mean());x=(t4-center)/20
    design=np.column_stack([np.ones(len(x)),x,x*x,x*x*x])
    lifted=np.unwrap(y4*2*np.pi/ALIAS_HZ)*ALIAS_HZ/(2*np.pi)
    coefficient=np.linalg.lstsq(design,lifted,rcond=None)[0]
    inside=(t5>=t4.min())&(t5<=t4.max());xx=(t5[inside]-center)/20
    prediction=np.column_stack([np.ones(len(xx)),xx,xx*xx,xx*xx*xx])@coefficient
    d=circular(y5[inside]-prediction*(rf5/rf4));offset=float(np.mean(d));r=circular(d-offset)
    dt=t5[inside]-np.mean(t5[inside]);slope=float(dt@r/(dt@dt))
    return dict(count=int(inside.sum()),rf_ratio=float(rf5/rf4),constant_difference_hz=offset,
        constant_removed_rms_hz=float(np.sqrt(np.mean(r*r))),residual_slope_hz_s=slope)


def main():
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz');ctx=json.loads((ROOT/'context.json').read_text())
    base=json.loads((ROOT/'baseline.json').read_text());cal=np.load(ROOT/'calibration-components.npz')
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector'])
    groups=base['groups'][1:];rows=[np.array(extend_continuity(a,link_segments(g['continuity_segments'])[0],a[g['name']+'_all_rows'])) for g in groups]
    obs=[observations(a,ctx,r) for r in rows]
    rf=[float(np.unique(o.rf_hz)[0]) for o in obs]
    ys=[a['measured'][r]-a['correction'][r] for r in rows]
    splits={split:[np.ones(len(r),bool) if split=='all' else (o.times_s<=np.median(o.times_s) if split=='early_to_late' else o.times_s>np.median(o.times_s)) for o,r in zip(obs,rows)] for split in ['all','early_to_late','late_to_early']}
    state={(mode,split):dict(score=np.full(len(bank.numbers),np.inf),timing=np.zeros(len(bank.numbers)),
        offset=np.zeros((2,len(bank.numbers))),train=np.zeros((2,len(bank.numbers))),test=np.zeros((2,len(bank.numbers))))
        for mode in ['recorded_rf','equal_rf_control'] for split in splits}
    for shift in np.linspace(-20,20,401):
        predictions=[predict_orbits(bank,o,prior,v[:2],np.full(len(bank.numbers),shift),derivatives=False)[:2] for o in obs]
        for mode in ['recorded_rf','equal_rf_control']:
            for split,masks in splits.items():
                metrics=[];eligible=np.ones(len(bank.numbers),bool)
                for j,(yy,(pred,vis),mask) in enumerate(zip(ys,predictions,masks)):
                    scale=rf[0]/rf[j] if mode=='equal_rf_control' else 1.
                    residual=circular(yy[:,None]-pred*scale)
                    metrics.append(offset_fit(residual,mask));eligible &= vis[mask].all(axis=0)
                score=sum(mask.sum()*(m[1]/125)**2 for mask,m in zip(masks,metrics))+(shift/2)**2
                score[~eligible]=np.inf;s=state[mode,split];take=score<s['score']
                s['score'][take]=score[take];s['timing'][take]=shift
                for j,m in enumerate(metrics):
                    for key,value in [('offset',m[0]),('train',m[1]),('test',m[2])]:s[key][j,take]=value[take]
    searches=[]
    for (mode,split),s in state.items():
        ranked=[]
        for k in np.argsort(s['score'])[:8]:
            ranked.append(dict(satellite=int(bank.numbers[k]),retained=int(bank.numbers[k]) in base['retained_candidates'],
                timing_s=float(s['timing'][k]),score=float(s['score'][k]),
                tracks=[dict(group=g['name'],count=len(r),offset_hz=float(s['offset'][j,k]),training_rms_hz=float(s['train'][j,k]),
                    test_rms_hz=float(s['test'][j,k]) if split!='all' else None) for j,(g,r) in enumerate(zip(groups,rows))]))
        searches.append(dict(rf_mode=mode,split=split,ranked=ranked))
    empirical={}
    for mode in ['published','no_clock','raw']:
        empirical[mode]=normalized_difference(obs[0].times_s,a['measured'][rows[0]]-cal[mode][rows[0]],rf[0],
            obs[1].times_s,a['measured'][rows[1]]-cal[mode][rows[1]],rf[1])
    result=dict(groups=[dict(name=g['name'],rows=r.tolist(),rf_hz=f) for g,r,f in zip(groups,rows,rf)],
        empirical_normalized_doppler_difference=empirical,searches=searches,
        qualification='Conditional same-satellite/common-timing test for simultaneous tracks. Each '
        'track has a separate fitted constant offset; same candidate and timing must explain both. '
        'Candidate and timing are chosen on training halves only. Calibration, position and '
        'continuity membership come from the full scan. Equal-RF control intentionally applies '
        'the CH4 RF to both predictions; it is not a physical mapping proposal.')
    (ROOT/'cross-band.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(empirical=empirical,searches=[dict(rf_mode=s['rf_mode'],split=s['split'],best=s['ranked'][0]) for s in searches]),indent=2),flush=True)


if __name__=='__main__':main()
