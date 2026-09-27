"""Build portable, receipt-derived figures for the RX-geometry report."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import argparse
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]; B=ROOT/'reports/2026_09_27_roof_balanced_confirmation'
SOURCES={
 'initial':ROOT/'reports/2026_09_27_roof_location_geometry/measured_distance_results.json',
 'balanced_dev':ROOT/'reports/2026_09_27_roof_geometry_confirmation/balanced_development_distances.json',
 'balanced':B/'distance_results.json','mixture':B/'mixture-geometry-distances.json',
 'shared':B/'shared-geometry-distances.json','dual':B/'dual-shared-geometry-distances.json',
 'calibration':B/'mixture_calibration_polished.json','attribution':B/'dual-track-attribution.json',
 'detection':B/'track_random_intercept_refined.json','ratio':B/'ratio_random_intercept.json',
 'transfer':B/'association-transfer-summary.json'}

def sha(p): return 'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
def load(): return {k:json.loads(p.read_text()) for k,p in SOURCES.items()}
def save(fig,name):
 (HERE/'figures').mkdir(parents=True,exist_ok=True); fig.tight_layout()
 for ext in ('png','svg'):
  output=HERE/'figures'/f'{name}.{ext}'
  fig.savefig(output,dpi=180,bbox_inches='tight')
  if ext=='svg': output.write_text('\n'.join(line.rstrip() for line in output.read_text().splitlines())+'\n')
 plt.close(fig)
def label(s): return s.replace('scan-fw-','')[:5]
def rows_by(d): return {(r['session_id'],r['prior']):r for r in d['rows']}

def build_data(x):
 keys=sorted(rows_by(x['dual']))
 geo=[]
 for k in keys:
  m=rows_by(x['mixture'])[k]['errors_km']; s=rows_by(x['shared'])[k]['errors_km']; q=rows_by(x['dual'])[k]['errors_km']
  geo.append({'session_id':k[0],'prior':k[1],'D':m['D'],'old':m['old'],'mean':m['mean'],
              'mixture':m['mixture'],'shared_detection':s['shared'],'dual_shared':q['dual']})
 cal=[]
 for fold in x['calibration']['conditional_loso']:
  cal.append({'session_id':fold['session_id'],'track_count':fold['track_count'],
              **{a:fold['models'][a]['joint_nll_sum']/fold['track_count'] for a in ('M0','mean','mixture')}})
 sig=[]
 for sid in x['calibration']['calibration_sessions']:
  ds=json.loads((B/f'track-random-intercept-refined-fold-{sid}.json').read_text())
  rs=json.loads((B/f'ratio-random-intercept-fold-{sid}.json').read_text())
  sig.append({'session_id':sid,'detection_sigma':ds['models']['mixture']['sigma_selection']['sigma'],
              'ratio_tau':rs['models']['mixture']['tau_selection']['tau']})
 attr=next(r for r in x['attribution']['comparisons'] if r['session_id']=='scan-fw-339af454a2aab2f4' and r['prior']=='sacramento' and r['from']=='D' and r['to']=='dual' and r['variant']=='dual')
 transfer=[]
 for sid,dirs in x['transfer']['summary']['recordings'].items():
  for direction,value in dirs.items():
   transfer.append({'session_id':sid,'direction':direction,
     **{mode:value['metrics'][mode]['improvement_baseline_minus_reception']['occupied_second_weighted']
        for mode in ('normal','reversed','null')}})
 return {'geographic_rows':geo,'calibration_loso':cal,'fold_random_effects':sig,
         'search_development_rows':x['balanced_dev']['rows'],
         'association_transfer':transfer,
         'single_case_decomposition':{'session_id':attr['session_id'],'prior':attr['prior'],**attr['totals']},
         'source_sha256':{k:sha(p) for k,p in SOURCES.items()}}

def figures(d):
 geo=d['geographic_rows']; models=['D','old','mean','mixture','shared_detection','dual_shared']; colors=plt.cm.viridis(np.linspace(.1,.9,len(models)))
 fig,ax=plt.subplots(figsize=(9,4.5)); x=np.arange(len(models)); w=.34
 site_colors={'sacramento':'#4c72b0','reno':'#dd8452'}
 for j,p in enumerate(('sacramento','reno')):
  means=[np.mean([r[m] for r in geo if r['prior']==p]) for m in models]
  ax.bar(x+(j-.5)*w,means,w,label=p.title(),color=site_colors[p],edgecolor='white',linewidth=.6)
 ax.set(xticks=x,xticklabels=['D','Original','Mean','Mixture','Shared det.','Dual shared'],ylabel='Mean location error (km)',title='Matched 4-recording grid: six frozen objectives');ax.legend(loc='upper center',bbox_to_anchor=(.5,-.14),ncol=2,frameon=False);fig.subplots_adjust(bottom=.23);save(fig,'01_six_model_mean_error')

 fig,ax=plt.subplots(figsize=(10,4)); mat=np.array([[r[m]-r['D'] for m in models[1:]] for r in geo]); lim=max(.1,np.max(abs(mat)))
 im=ax.imshow(mat,aspect='auto',cmap='RdBu_r',vmin=-lim,vmax=lim);ax.set_xticks(range(5),['Original','Mean','Mixture','Shared det.','Dual shared']);ax.set_yticks(range(8),[label(r['session_id'])+' '+r['prior'][:3] for r in geo]);
 for i in range(8):
  for j in range(5): ax.text(j,i,f'{mat[i,j]:+.2f}',ha='center',va='center',fontsize=8)
 ax.set_title('Signed error change from Doppler baseline (negative improves)');fig.colorbar(im,ax=ax,label='Δ error (km)');save(fig,'02_case_change_heatmap')

 fig,ax=plt.subplots(figsize=(11,5)); xx=np.arange(len(geo))
 for m,c in zip(('D','old','dual_shared'),('#555','#dd8452','#4c72b0')): ax.plot(xx,[r[m] for r in geo],'-o',label=m.replace('_',' '),color=c)
 ax.set_yscale('log');ax.set_xticks(xx,[label(r['session_id'])+'\n'+r['prior'][:3] for r in geo]);ax.set(ylabel='Location error (km, log scale)',title='Per-case Doppler, original RX geometry, and latest dual-shared model');ax.legend();save(fig,'03_per_case_paired')

 fig,(ax,ax2)=plt.subplots(1,2,figsize=(12,4.6));cal=d['calibration_loso'];xx=np.arange(6)
 for arm,color,marker in (('M0','#777','o'),('mean','#55a868','s'),('mixture','#4c72b0','^')):
  ax.plot(xx,[r[arm] for r in cal],marker=marker,label=arm,color=color)
 ax.set_xticks(xx,[label(r['session_id']) for r in cal]);ax.set_ylabel('Held-track joint NLL / track');ax.set_title('A. Reception calibration cohort\n6 leave-one-recording-out folds');ax.legend(frameon=False)
 for p,color,marker in (('sacramento','#4c72b0','o'),('reno','#dd8452','s')):
  means=[np.mean([r[m] for r in geo if r['prior']==p]) for m in models]
  ax2.plot(np.arange(6),means,marker=marker,label=p.title(),color=color)
 ax2.set_xticks(range(6),['D','Original','Mean','Mixture','Shared\ndet.','Dual\nshared']);ax2.set_ylabel('Mean location error (km)');ax2.set_title('B. Geographic evaluation cohort\n4 recordings × 2 independent priors');ax2.legend(frameon=False)
 fig.suptitle('Separate cohorts and estimands — no fold-to-case correspondence',fontsize=12,y=1.03);save(fig,'04_predictive_vs_geographic_cohorts')

 dev=d['search_development_rows'];fig,ax=plt.subplots(figsize=(10,4)); xx=np.arange(len(dev));ax.plot(xx,[r['original_d_km'] for r in dev],'o-',label='Greedy/original D');ax.plot(xx,[r['balanced_d_km'] for r in dev],'o-',label='Depth-balanced D');ax.set_yscale('log');ax.set_xticks(xx,[label(r['session_id'])+'\n'+r['prior'][:3] for r in dev]);ax.set(ylabel='Error (km, log scale)',title='Search-policy development comparison');ax.legend();save(fig,'05_search_policy_log_error')

 a=d['single_case_decomposition'];names=['D','Detection','Ratio'];vals=[a['delta_D'],a['delta_detection_increment'],a['delta_conditional_ratio_increment']];fig,ax=plt.subplots(figsize=(6.5,4));ax.bar(names,vals,color=['#777','#55a868','#c44e52']);ax.axhline(0,color='black',lw=.8);ax.set(ylabel='Weighted score change',title=f"Exact score decomposition: {label(a['session_id'])} Sacramento\nD → dual selected point");ax.text(2.0,max(vals),f"Joint Δ = {a['delta_joint']:+.4g}",ha='right');save(fig,'06_single_case_score_decomposition')

 sig=d['fold_random_effects'];fig,ax=plt.subplots(figsize=(8,4));xx=np.arange(6);ax.plot(xx,[r['detection_sigma'] for r in sig],'o-',label='Detection σ');ax.set_xticks(xx,[label(r['session_id']) for r in sig]);ax.set_ylabel('Detection shared-effect σ');ax2=ax.twinx();ax2.plot(xx,[r['ratio_tau'] for r in sig],'s--',color='#c44e52',label='Ratio τ');ax2.set_ylabel('Ratio shared-effect τ');ax.set_title('Frozen leave-one-recording-out nuisance scales');h,l=ax.get_legend_handles_labels();h2,l2=ax2.get_legend_handles_labels();ax.legend(h+h2,l+l2);save(fig,'07_fold_random_effects')

 tr=d['association_transfer']; sessions=sorted({r['session_id'] for r in tr});fig,ax=plt.subplots(figsize=(9,4));xx=np.arange(6);w=.34
 for j,direction in enumerate(('A_to_B','B_to_A')):
  vals=[next(r['normal'] for r in tr if r['session_id']==s and r['direction']==direction) for s in sessions]
  rev=[next(r['reversed'] for r in tr if r['session_id']==s and r['direction']==direction) for s in sessions]
  ax.bar(xx+(j-.5)*w,vals,w,label=direction.replace('_','→'),alpha=.8);ax.scatter(xx+(j-.5)*w,rev,marker='x',color='black',s=25)
 ax.axhline(0,color='black',lw=.8);ax.set_xticks(xx,[label(s) for s in sessions]);ax.set(ylabel='Baseline − RX predictive NLL',title='Exploratory temporal conditional association transfer\nBars: normal direction; ×: reversed directional control');ax.legend();save(fig,'08_association_transfer')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--extract',action='store_true',help='re-extract plot_data.json from workspace source receipts');args=parser.parse_args()
 HERE.mkdir(parents=True,exist_ok=True); data_path=HERE/'plot_data.json'
 if args.extract or not data_path.exists():
  d=build_data(load());data_path.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
 else:d=json.loads(data_path.read_text())
 figures(d)
 manifest={'generator_sha256':sha(Path(__file__)),'plot_data_sha256':sha(data_path),'source_sha256':d['source_sha256'],'figures':sorted(p.name for p in (HERE/'figures').glob('*'))}
 (HERE/'figure_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
