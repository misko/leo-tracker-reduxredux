exec(open('/tmp/compare_space_track_pipeline.py').read().replace("print(json.dumps(result,indent=2))",''))
from leo.analysis.shared_scan_model import bounded_shared_fit
from leo.application.shared_fast_position import plain
validation=json.loads((root/'track_validation.json').read_text());newsh=shifts.copy()
for num in [69433,69333]:
 row=next(r for r in validation if r['satellite']==num and r['mode']=='timing_only' and r['split']=='all');newsh[nums.index(num)]=row['timing_s']
seed=v.copy();seed[7]=newsh.mean();seed[8:]=zero_sum_basis(len(nums)).T@(newsh-seed[7])
def summary(vv,nn):
 e=model.evaluate_joint(vv,nn);terms=e[3];best=terms.responsibilities.argmax(axis=1);ass=terms.responsibilities[np.arange(len(best)),best]>terms.clutter_probability
 out=dict(objective=float(e[0]),nll=float(terms.nll),associated=int(ass.sum()),tracks=[])
 for name,path in [('CH2 170–190 s','/tmp/rx1-ch2-170-190'),('CH2 50–75 s','/tmp/rx1-ch2-50-75'),('CH4 40–100 s','/tmp/rx1-ch4-40-100')]:
  rows=np.load(path+'/arrays.npz')['rows']
  if '50–75' in name:rows=rows[np.isin(obs.times_s[rows],json.loads(Path(path+'/track_summary.json').read_text())['times'])]
  out['tracks'].append(dict(track=name,count=len(rows),associated=int(ass[rows].sum()),assignments={str(num):int(np.sum(ass[rows]&(best[rows]==k))) for k,num in enumerate(nums) if np.any(ass[rows]&(best[rows]==k))}))
 return out
initial=dict(original=summary(v,n),track_seed=summary(seed,n));(root/'track_seed_initial.json').write_text(json.dumps(initial,indent=2)+'\n');print(json.dumps(initial),flush=True)
fitted=bounded_shared_fit(model,seed,n,local_center=v[:2],local_radius_km=25)
(root/'track_seed_fit.json').write_text(json.dumps(plain(fitted),indent=2)+'\n')
if 'fit' in fitted:
 final=summary(np.array(fitted['fit']['vector']),np.array(fitted['fit']['nuisance']));final['audit']=plain(fitted.get('audit'));(root/'track_seed_result.json').write_text(json.dumps(final,indent=2)+'\n');print(json.dumps(final),flush=True)
else:print(json.dumps(plain(fitted)),flush=True)
