"""Local timing-only refinements for three visually identified scan-B ridges."""
import csv,json,argparse
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.optimize import minimize_scalar
from exhaustive_subset import Case,HERE,circular_residual,competitive_addition_scores,timing_prior
from plot_tle_doppler_overlay import calibrated_points,orbital_curve
from plot_subset_orbits import alias_background


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--remaining',action='store_true');remaining=parser.parse_args().remaining
 c=Case('B'); d=c.data; out=HERE/'gray-ridge-audit'
 saved=json.loads((HERE/'exhaustive-subset/B-receipt.json').read_text());f=saved['arms']['fitted-c']['fit']
 c.params=np.array(f['parameters']); c.coeff=np.array(f['rf_coefficient_hz_per_ghz'])
 c.selected=[int(np.flatnonzero(d.numbers==n)[0]) for n in saved['catalog_numbers']]
 common=float(np.mean(c.params[6+np.array(c.selected)]))
 baseline=c.evaluate()[1]
 records=list(csv.DictReader((HERE/'exhaustive-subset/B-fitted-c-assignments.csv').open()))
 assigned=np.array([int(r['row_index']) for r in records]); pred,vis=c.predict(c.selected)
 rx=np.array(d.receiver,int); nuisance=c.params[2+2*rx]+c.params[3+2*rx]*(d.times-d.reference_time_s)+c.features@c.coeff
 points=calibrated_points(d.measured,pred,d.rf,nuisance,c.prepared.alias_hz)
 rr,cc=alias_background(points['alias_integer'],assigned)
 mask=(rx[rr]==1)&(d.times[rr]<=75); rr,cc=rr[mask],cc[mask]; y=points['doppler_hz'][rr,cc]/1000
 fig,(ax,resax)=plt.subplots(2,1,figsize=(14,10),gridspec_kw={'height_ratios':[2,1]},sharex=True)
 ax.scatter(d.times[rr],y,c='.7',s=7,alpha=.6,label='Other unassigned / alias alternatives')
 summaries=[]
 candidates=[('main',62152,3.5,'#0072B2'),('lower',66375,.25,'#D55E00'),('early',62435,0.,'#009E73')]
 if remaining:candidates=[('remaining_late',69352,-.5,'#CC79A7'),('remaining_early',66231,.25,'#8B4513')]
 for name,number,offset,color in candidates:
  source=out/f'{name}-screen.json'
  if not source.exists(): source=out/'screen.json'
  targets=np.array(json.loads(source.read_text())['target_rows'])
  index=int(np.flatnonzero(d.numbers==number)[0]);params=c.params.copy()
  def prediction(shift):
   params[6+index]=common+shift
   return c.predict([index],params)[0][:,0]
  coarse=circular_residual(d.measured,prediction(offset),c.prepared.alias_hz)
  # One nearest hypothesis per probe, selected once before continuous fitting.
  selected=[]
  for group in np.unique(d.group[targets]):
   rows=targets[d.group[targets]==group]
   row=rows[np.argmin(np.abs(coarse[rows]))]
   if abs(coarse[row])<1500: selected.append(row)
  selected=np.array(selected)
  def loss(shift):
   residual=circular_residual(d.measured[selected],prediction(shift)[selected],c.prepared.alias_hz)
   return float(np.mean(residual**2))
  optimized=minimize_scalar(loss,bounds=(offset-.3,offset+.3),method='bounded',options={'xatol':1e-8})
  shift=float(optimized.x);raw=prediction(shift)
  residual=circular_residual(d.measured,raw,c.prepared.alias_hz)
  normalized=residual*11.085e9/d.rf
  p,v=c.predict([index],params)
  score=competitive_addition_scores(c.prepared,baseline,p,v,c.pdet)
  oldprior=timing_prior(c.params[6+np.array(c.selected)])
  gain=float(score['log_likelihood_change'][0])-c.penalty-timing_prior(np.r_[c.params[6+np.array(c.selected)],common+shift])+oldprior
  if index in c.selected:gain=None
  hits=(rx==1)&(d.times<75)&(np.abs(residual)<500)&v[:,0]&~np.isin(np.arange(len(rx)),assigned)
  # Show all display aliases of the supported rows in the screenshot region.
  matching=np.isin(rr,np.flatnonzero(hits))
  ax.scatter(d.times[rr[matching]],y[matching],s=13,color=color,label=f'{number}: matching measurements + alias copies')
  physical_points=calibrated_points(d.measured,p,d.rf,nuisance,c.prepared.alias_hz)
  ax.scatter(d.times[hits],physical_points['doppler_hz'][hits,0]/1000,s=15,color=color)
  tt=np.arange(0,75.001,.1);curve,visible=orbital_curve(d,params,[index],tt)
  ax.plot(tt,np.where(visible[:,0],curve[:,0]/1000,np.nan),color=color,lw=2,label=f'{number}: physical orbit')
  resax.scatter(d.times[selected],normalized[selected],s=17,color=color,label=str(number))
  screen=next(x for x in saved['screens'][-1]['candidates'] if x['catalog_number']==number)
  summary=dict(catalog_number=number,offset_from_common_s=shift,total_timing_s=common+shift,
               frozen_probe_count=len(selected),start_s=float(min(d.times[selected])),end_s=float(max(d.times[selected])),
               rms_native_hz=float(np.sqrt(loss(shift))),rms_normalized_hz=float(np.sqrt(np.mean(normalized[selected]**2))),
               unassigned_early_rx1_groups_within_500hz=len(np.unique(d.group[hits])),
               global_log_likelihood_gain=float(score['log_likelihood_change'][0]),global_penalized_gain=gain,
               previous_screen=screen,rows=selected.tolist(),success=bool(optimized.success))
  if index in c.selected:
   summary['global_log_likelihood_gain']=None
   assigned_clusters={int(c.prepared.original_to_unique[row]) for row in assigned}
   summary['target_rows_exact_alias_copies_of_assigned']=sum(int(c.prepared.original_to_unique[row]) in assigned_clusters for row in targets)
   same_group={int(r['group']) for r in records if int(r['catalog_number'])==number}
   summary['target_groups_with_same_satellite_already_assigned']=len(set(map(int,d.group[targets]))&same_group)
   summary['target_rows']=len(targets)
   summary['target_groups']=len(np.unique(d.group[targets]))
  summaries.append(summary);print(json.dumps({k:v for k,v in summary.items() if k!='rows'}),flush=True)
 ax.set_ylim(-360,280);ax.set_ylabel('Calibrated Doppler (kHz)');ax.legend(ncol=2,fontsize=9)
 resax.axhline(0,color='.4',lw=1);resax.set_ylabel('GLRT − orbit (Hz)');resax.set_xlabel('Receive time (s)');resax.legend()
 for a in (ax,resax):a.set_xlim(0,75);a.grid(alpha=.2)
 fig.suptitle('Scan B RX1 · '+('remaining gray ridges' if remaining else 'candidate identifications for the early gray ridges')+'\nContinuous timing-only fits; receiver/RF calibration and known position unchanged')
 fig.text(.5,.012,'Colored repeated branches reuse the same measurements. Solid curves show physical orbit Doppler.\nResiduals use one frozen peak hypothesis per probe; in-sample candidate evidence, not confirmed identity. Existing assignments unchanged.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.06,1,.94));fig.savefig(out/('remaining-identified.png' if remaining else 'identified-ridges.png'),dpi=160)
 (out/('remaining-refined.json' if remaining else 'refined.json')).write_text(json.dumps(dict(scope=__doc__,common_timing_s=common,candidates=summaries),indent=2))


if __name__=='__main__':main()
