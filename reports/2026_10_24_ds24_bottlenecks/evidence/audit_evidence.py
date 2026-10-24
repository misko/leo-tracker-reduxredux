"""Read-only evidence audit of all 24 common DS24 scans; no RF or refitting."""
import csv
import json
from pathlib import Path
import numpy as np

OUT = Path(__file__).resolve().parent
FULL = Path('/srv/bulk/leo/research/ds25-20261024')
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
ROOTS = {'all_channels': FULL, 'ch1_4': HALF/'ch1_4', 'ch5_8': HALF/'ch5_8'}
ARMS = ('c0', 'fitted_c')

def read(p):
    return json.loads(p.read_text())

def write(p, d):
    p.write_text(json.dumps(d, indent=2, default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v.item())+'\n')

def summary(x):
    x=np.asarray(x, float)
    return dict(n=len(x),mean=float(x.mean()),median=float(np.median(x)),p05=float(np.quantile(x,.05)),p95=float(np.quantile(x,.95)),maximum=float(x.max())) if len(x) else dict(n=0)

def labels(saved, entries):
    result={}
    entry_labels={e['component']:int(e['norad']) for e in entries}
    for row in saved['gates']['tracks']+saved.get('linear_gates',[]):
        if not row['compatible']: continue
        for oid in row['observation_ids']:
            if oid in result: raise ValueError('multiply owned observation')
            result[oid]=int(row.get('norad',entry_labels.get(row['component'])))
    assert len(result)==saved['active_points']+saved.get('predictive_points',saved.get('additional_predictive_points',0))
    return result

def quick():
    cases=read(HALF/'summary.json')['baseline']['c0']['common_cases']
    records=[];comparisons=[];lookup={};raw=[]
    for case in cases:
        by={}
        for group,root in ROOTS.items():
            cavity=read(root/'family_cavity/position'/(case+'.json'))
            saved=cavity['policy_arms']
            entries=cavity['selected']['entries'] if cavity['accepted'] else cavity['baseline_entries']
            observations=read(root/case/'observations.json')
            obs={o['observation_id']:o for o in observations}
            noise=read(root/case/'radio_noise.json')
            tracking=read(root/case/'tracking.json')
            raw.append(dict(case=case,group=group,sample_rate_hz=tracking['source']['sample_rate_hz'],probe_ms=tracking['source']['probe_ms'],**{k:noise[k] for k in ('constant_radio_sigma_hz','floor_sigma_hz','noise_samples')}))
            for arm in ARMS:
                fit=saved[arm];lab=labels(fit,entries);by[(group,arm)]=(lab,obs,fit)
                families=set(lab.values())
                curved=set(r['norad'] for r in fit['gates']['tracks'] if r['compatible'])
                records.append(dict(case=case,group=group,arm=arm,GLRT=len(obs),associated=len(lab),families=len(families),curved_families=len(curved),curved_points=fit['active_points'],predictive_points=len(lab)-fit['active_points'],RMS_hz=fit['RMS_hz'],endpoint_latlon=fit['endpoint_latlon'],phase_abs_s=summary(abs(np.asarray(fit['phase_reference'])))))
                lookup[(case,group,arm)]=lab
        for group in ('ch1_4','ch5_8'):
            for arm in ARMS:
                full,fo,ff=by[('all_channels',arm)];half,ho,hf=by[(group,arm)]
                assert set(ho)<=set(fo)
                assert all(ho[k]==fo[k] for k in ho)
                common=set(full)&set(half)
                contradiction=[k for k in common if full[k]!=half[k]]
                full_local=set(full)&set(ho)
                counts={}
                for k in contradiction:
                    key=f'{full[k]}->{half[k]}'
                    counts[key]=counts.get(key,0)+1
                a,b=np.radians([ff['endpoint_latlon'],hf['endpoint_latlon']]);dv=b-a
                h=np.sin(dv[0]/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin(dv[1]/2)**2
                comparisons.append(dict(case=case,group=group,arm=arm,GLRT=len(ho),full_associated_in_subset=len(full_local),half_associated=len(half),both_associated=len(common),same_identity=len(common)-len(contradiction),identity_disagreements=len(contradiction),full_only=len(full_local-set(half)),half_only=len(set(half)-full_local),neither=len(set(ho)-(full_local|set(half))),largest_reassignments=sorted(counts.items(),key=lambda x:-x[1])[:8],endpoint_separation_km=float(12742*np.arcsin(np.sqrt(h)))))
    aggregates={}
    for group in ROOTS:
        for arm in ARMS:
            rr=[r for r in records if r['group']==group and r['arm']==arm]
            aggregates[f'{group}/{arm}']={k:summary([r[k] for r in rr]) for k in ('GLRT','associated','families','curved_families','curved_points','predictive_points','RMS_hz')}
    agreement={}
    for group in ('ch1_4','ch5_8'):
        for arm in ARMS:
            rr=[r for r in comparisons if r['group']==group and r['arm']==arm]
            sums={k:sum(r[k] for r in rr) for k in ('GLRT','full_associated_in_subset','half_associated','both_associated','same_identity','identity_disagreements','full_only','half_only','neither')}
            sums.update(identity_agreement_percent_of_both=100*sums['same_identity']/sums['both_associated'],changed_ownership_percent_of_GLRT=100*(sums['identity_disagreements']+sums['full_only']+sums['half_only'])/sums['GLRT'],scans_with_identity_disagreement=sum(r['identity_disagreements']>0 for r in rr),endpoint_separation_km=summary([r['endpoint_separation_km'] for r in rr]))
            agreement[f'{group}/{arm}']=sums
    output=dict(cases=cases,records=records,comparisons=comparisons,aggregates=aggregates,agreement=agreement,radio_noise=raw)
    write(OUT/'evidence_quick.json',output)
    print(json.dumps(dict(agreement=agreement,radio_noise={g:{k:summary([r[k] for r in raw if r['group']==g]) for k in ('constant_radio_sigma_hz','floor_sigma_hz')} for g in ROOTS},family_counts={k:v['curved_families'] for k,v in aggregates.items()}),indent=2),flush=True)
    return cases

def residuals(cases):
    import algo02_scan as algo
    import probe_ds23_graph_seeded_paths as paths
    tracks=[];families=[];point_rows=[]
    for case in cases:
        for group,root in ROOTS.items():
            algo.bind_run_directory(root)
            saved=read(root/'family_cavity/position'/(case+'.json'))
            selected=saved['selected'] if saved['accepted'] else None
            d=dict(scan=algo.load_scan(root,case),keep=np.asarray(saved['original_mask'],bool),
                powers=np.asarray(saved['powers']),model=saved['model'],arms=saved['policy_arms'],
                node=selected['node'] if selected else saved['baseline_node'],
                entries=selected['entries'] if selected else saved['baseline_entries'],
                means=np.asarray(selected['means'] if selected else saved['baseline_means']))
            for arm in ARMS:
                fit=d['arms'][arm];x=np.asarray(fit['endpoint_east_north_km'])
                p=paths.build(d,'default',arm,fit['phase_reference']);c=p.calculate(x)
                residual=c['conditional_residual_hz'];state=p.state(x)
                for norad_index in p.labels:
                    families.append(dict(case=case,group=group,arm=arm,norad=int(d['scan'].norads[norad_index]),phase_s=float(state['phases'][norad_index])))
                for row,member,sl in zip(p.rows,p.members,p.slices,strict=True):
                    active=p.keep[sl]
                    if not active.any():continue
                    t=p.scan.tracks[member];r=residual[sl][active];ts=np.asarray(t['times'])[active]
                    sig=p.point_noise[sl][active]
                    centered=r-r.mean()
                    acf=float(centered[:-1]@centered[1:]/max(centered@centered,1e-12))
                    threshold=4/np.sqrt(len(r));half=len(r)//2
                    tracks.append(dict(case=case,group=group,arm=arm,component=row['component'],norad=int(row['candidate_norad']),receiver=t['receiver'],channel=t['channel'],points=len(r),span_s=float(np.ptp(ts)),RMS_hz=float(np.sqrt(np.mean(r*r))),mean_hz=float(r.mean()),lag1_acf=acf,legacy_acf_threshold=float(threshold),acf_exceeds_legacy_threshold=bool(abs(acf)>threshold),half_mean_step_hz=float(r[half:].mean()-r[:half].mean()),noise_sigma_median_hz=float(np.median(sig)),standardized_RMS=float(np.sqrt(np.mean((r/sig)**2))),noise_precision=float(c['noise_precision'][list(p.slices).index(sl)])))
                    for oid,time,value,sigma in zip(np.asarray(t['observation_ids'])[active],ts,r,sig,strict=True):
                        point_rows.append(dict(case=case,group=group,arm=arm,observation_id=str(oid),norad=int(row['candidate_norad']),receiver=t['receiver'],channel=t['channel'],time_s=float(time),residual_hz=float(value),sigma_hz=float(sigma)))
            write(OUT/'residuals.partial.json',dict(tracks=tracks,families=families))
            print(case,group,'complete',flush=True)
    write(OUT/'residuals.json',dict(tracks=tracks,families=families))
    with (OUT/'curved_point_residuals.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(point_rows[0]));writer.writeheader();writer.writerows(point_rows)

if __name__=='__main__':
    import sys
    cases=read(OUT/'evidence_quick.json')['cases'] if '--residuals' in sys.argv and (OUT/'evidence_quick.json').exists() else quick()
    if '--residuals' in sys.argv:residuals(cases)
