exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.application.channel_group_refinement import objective
from leo.analysis.shared_scan_model import SharedScanObjective,donor_state,bounded_shared_fit
from leo.application.shared_fast_position import plain
joint=objective(SimpleNamespace(observations=obs),bank,prior,np.array(new['provenance']['clock_nodes_s']))
donor=stages[f"B-{stages['source-selection']['B_index']}"]['result'];assert donor['audit']['accepted']
raw,shift,_,_,transport=donor_state(joint,donor['fit'])
research=SharedScanObjective(raw,shift)
previous=stages['shared-all-B-all']['result'];vv=np.array(previous['fit']['vector']);nn=np.array(previous['fit']['nuisance'])
target_sets=[]
for name,path in [('early_ch2','/tmp/rx1-ch2-50-75'),('ch4','/tmp/rx1-ch4-40-100'),('late_ch2','/tmp/rx1-ch2-170-190')]:
    rows=np.load(path+'/arrays.npz')['rows']
    if name=='early_ch2':rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
    target_sets.append((name,rows))
def summarize(vector,nuisance):
    ee=research.evaluate_joint(vector,nuisance);t=ee[3];b=t.responsibilities.argmax(axis=1);p=t.responsibilities[np.arange(len(b)),b];a=p>t.clutter_probability
    out=dict(objective=float(ee[0]),nll=float(t.nll),associated=int(a.sum()),tracks=[])
    for name,rows in target_sets:
        counts={str(num):int(np.sum(a[rows]&(b[rows]==k))) for k,num in enumerate(nums)};counts={k:v for k,v in counts.items() if v}
        chosen=int(np.bincount(b[rows][a[rows]],minlength=len(nums)).argmax()) if a[rows].any() else int(np.argmin(np.mean(t.residual_hz[rows]**2,axis=0)))
        out['tracks'].append(dict(track=name,count=len(rows),associated=int(a[rows].sum()),assignments=counts,most_common_satellite=nums[chosen],all_target_rms_hz=float(np.sqrt(np.mean(t.residual_hz[rows,chosen]**2)))))
    return out
before=summarize(vv,nn);print(json.dumps(dict(previous_audit=previous['audit'],before=before)),flush=True)
fit=bounded_shared_fit(research,vv,nn,local_center=vv[:2],local_radius_km=25)
result=dict(qualification='Bounded continuation of the original complete-data B candidate. Same observations, satellite bank, likelihood, priors, frozen donor band contrast and strict convergence gate. No track-specific timing or band correction is added. This complete-data fit is not a holdout experiment.',previous_audit=previous['audit'],donor_transport_error_hz=transport,before=before,fit=plain(fit),after=summarize(np.array(fit['fit']['vector']),np.array(fit['fit']['nuisance'])) if fit.get('fit') else None)
(root/'original_full_B_continuation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['previous_audit','before','after']},indent=2),flush=True);print(json.dumps(fit['audit']),flush=True)
