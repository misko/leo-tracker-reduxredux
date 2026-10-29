"""Summarize frozen promotion tests; evaluation GPS enters only here."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from debug_fast_graph_unassociated import read, write
from report_graph_covariance_qualification import error_km, SITE
from validate_fast_target_guard import target_guard
from stress_joint_attachment import KINDS

METHODS=('white_existing','covariance_existing','covariance_physical')
LABELS=('White + existing tests','Covariance + existing tests','Covariance + physical tests')
ARMS=('c0','fitted_c')


def rejection(v, method):
    reasons=[]
    if not v['identity_pass']:reasons.append('identity comparison')
    if method!='white_existing' and not v['calibration_qualified']:reasons.append('covariance training penalty')
    if method!='white_existing' and not all(x>0 for x in v['held_density_gains'].values()):reasons.append('held density')
    if not (all(r['compatible'] for r in v['physical'].values()) if method=='covariance_physical' else v['existing_screen_pass']):reasons.append('initial structure')
    if not (all(r['compatible'] for r in v['final_physical'].values()) if method=='covariance_physical' else v['final_existing_pass']):reasons.append('final structure')
    if not v['final_original_gates_pass']:reasons.append('old gates or phase convergence')
    if not v['preserves_old_points']:reasons.append('old point preservation')
    if not all(r['target_min_elevation_deg']>=0 and all(abs(t['bias_hz'])<=3000 and t['raw_RMS_after_bias_hz']<=450 for t in r['physical_target_checks']) for r in v['proposal'].values()):reasons.append('absolute RMS/offset/visibility')
    return reasons


def run(args):
    out=args.output;out.mkdir(parents=True,exist_ok=False);study=args.study
    inventory=read(study/'promotion-inventory-v1/inventory.json')
    panel=study/'promotion-panel-v1';stress=study/'promotion-stress-v1'
    protocol=read(panel/'protocol.json');controls=[];rows=[];decisions=[]
    for job in read(stress/'protocol.json')['jobs']:
        terminal=read(stress/(job['name']+'-terminal.json'))
        for m in METHODS:
            path=stress/job['name']/(m+'.json');v=read(path) if path.exists() else None
            controls.append(dict(kind=job['kind'],seed=job['seed'],method=m,execution=terminal['status'],
                completed_variant=v is not None,accepted=v['accepted'] if v else None,candidate=v['candidate'] if v else None,
                reasons=rejection(v,m) if v else ['variant incomplete'],
                final_max={a:r['maximum_statistic'] for a,r in v['final_physical'].items()} if v else {}))
    for number,job in enumerate(protocol['jobs'],1):
        folder=panel/job['job_id'];terminal=read(folder/'terminal.json');attachment=folder/'attachment'
        reentry_path=folder/'reentry/result.json'
        source=read(reentry_path if reentry_path.exists() else folder/'reentry/fallback.json')
        unconstrained=read(folder/'reentry/unconstrained.json') if source['status']=='accepted' else None
        guarded=source['policy'] if target_guard(source,unconstrained) else source['support']
        apath=attachment/'result.json';aresult=read(apath) if apath.exists() else None
        variants={m:read(attachment/(m+'.json')) for m in METHODS if (attachment/(m+'.json')).exists()}
        # An incomplete job cannot adopt an intermediate variant.
        complete=terminal['status']=='complete'
        total=len(read(Path(job['root'])/'SCAN/observations.json'))
        decisions.append(dict(label=f'V{number:02}',recording=job['report_scalar_metadata']['recording_name'],
            job_id=job['job_id'],execution=terminal,status=aresult['status'] if aresult else 'incomplete',
            target_points=aresult.get('target_points',0) if aresult else 0,
            variants={m:dict(accepted=v['accepted'] and complete,candidate=v['candidate'],reasons=rejection(v,m),
                diagnostic_error_km={a:error_km(v['proposal'][a]['endpoint_latlon']) for a in ARMS},
                maximum_target_RMS_hz={a:max(t['raw_RMS_after_bias_hz'] for t in v['proposal'][a]['physical_target_checks']) for a in ARMS},
                common_margin=v['common_margin'],split_margin=v['split_margin']) for m,v in variants.items()}))
        if (attachment/'nomination.json').exists():
            nomination=read(attachment/'nomination.json')
            decisions[-1]['target_points']=sum(t['points'] for t in nomination['tracks'])
            decisions[-1]['represented_candidates']=nomination['candidates']
            decisions[-1]['unrepresented_candidates']=nomination['unrepresented']
        if 'covariance_physical' in variants:
            from leo.analysis.research.retained_track_likelihood import PERIOD
            v=variants['covariance_physical'];r=v['proposal']['fitted_c']
            tracks={t['key']:t for t in read(Path(job['root'])/'SCAN/tracks.json')}
            count=len(v['extras']);fig,axes=plt.subplots(2,count,figsize=(6*count,6),squeeze=False,layout='constrained')
            tt=np.asarray(r['target_times_s']);raw=np.asarray(r['target_raw_hz']);owner=np.asarray(r['target_owners'])
            for k,e in enumerate(v['extras']):
                track=tracks[e['component']];use=owner==k;bias=r['physical_target_checks'][k]['bias_hz']
                values=np.asarray(track['values'])+e['alias']*PERIOD
                axes[0,k].plot(tt[use],values/1000,'.',label='Nominated GLRT')
                axes[0,k].plot(tt[use],(values-raw[use]+bias)/1000,label=f'Trial orbit {v["candidate"]} + nuisance')
                axes[0,k].set(title=e['component'].split('-RF')[0],ylabel='CFO with graph alias (kHz)');axes[0,k].legend(fontsize=8)
                axes[1,k].plot(tt[use],raw[use]-bias,'.-');axes[1,k].axhline(0,color='black',lw=.7)
                axes[1,k].set(xlabel='Time (s)',ylabel='Trial residual after offset (Hz)')
            fig.suptitle(f'V{number:02}: accepted={v["accepted"] and complete}; '+', '.join(rejection(v,'covariance_physical')),fontsize=10)
            fig.savefig(out/f'V{number:02}_targets.png',dpi=150);plt.close(fig)
        for arm in ARMS:
            policies=dict(production=source['baseline'][arm],guarded=guarded[arm])
            policies.update({m:variants[m]['policy'][arm] if complete and m in variants else guarded[arm] for m in METHODS})
            for method,r in policies.items():
                rows.append(dict(label=f'V{number:02}',recording=job['report_scalar_metadata']['recording_name'],
                    execution=terminal['status'],arm=arm,method=method,total_GLRT=total,
                    associated=r['proposed_associated_points'],percent=100*r['proposed_associated_points']/total,
                    error_km=error_km(r['endpoint_latlon']),RMS_hz=r['RMS_hz'],score=r['negative_twice_elbo'],
                    displacement_from_guard_m=1000*float(np.linalg.norm(np.array(r['endpoint_east_north_km'])-guarded[arm]['endpoint_east_north_km'])),
                    curved=r['curved_points'],predictive=r['predictive_points'],postfit=r['postfit_only_points']))
    stats={}
    for arm in ARMS:
        stats[arm]={}
        for method in ('production','guarded')+METHODS:
            rr=[r for r in rows if r['arm']==arm and r['method']==method];e=np.array([r['error_km'] for r in rr])
            stats[arm][method]=dict(scans=len(rr),points=sum(r['associated'] for r in rr),
                  coverage=100*sum(r['associated'] for r in rr)/sum(r['total_GLRT'] for r in rr),
                  mean_km=float(e.mean()),median_km=float(np.median(e)),p95_km=float(np.percentile(e,95)),worst_km=float(e.max()))
    pilot=read(study/'joint-attachment-pilot/result.json')
    pilot_errors={a:dict(guarded=error_km(pilot['baseline'][a]['endpoint_latlon']),
          covariance_physical=error_km(pilot['variants']['covariance_physical']['policy'][a]['endpoint_latlon'])) for a in ARMS}
    shifts=[]
    for kind in ('step150','curvature250'):
        for seed in (4081,4082,4083):
            v=read(stress/f'{kind}-{seed}/covariance_physical.json')
            correct=read(stress/f'correct-{seed}/covariance_physical.json')
            shifts.append(dict(kind=kind,seed=seed,accepted=v['accepted'],
                displacement_from_matched_noise_control_m={a:1000*float(np.linalg.norm(
                    np.array(v['proposal'][a]['endpoint_east_north_km'])-correct['proposal'][a]['endpoint_east_north_km'])) for a in ARMS}))
    write(out/'summary.json',dict(controls=controls,rows=rows,decisions=decisions,stats=stats,
          pilot_errors_km=pilot_errors,injection_position_effects=shifts,
          evaluation_site=SITE,site_authority='User confirmed Oct 26–29 recordings during this experiment',
          inference_uses_GPS=False))
    with (out/'per_scan.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    plt.rcParams.update({'font.size':10,'axes.grid':True,'grid.alpha':.2})
    fig,ax=plt.subplots(figsize=(11,4),layout='constrained');x=np.arange(len(KINDS))
    for i,(m,label) in enumerate(zip(METHODS,LABELS)):
        counts=[sum(r['accepted'] is True for r in controls if r['kind']==k and r['method']==m) for k in KINDS]
        ax.bar(x+(i-1)*.25,counts,width=.25,label=label)
    ax.set(xticks=x,xticklabels=['Correct pair','Different satellites','Wrong continuous join','150 Hz step','300 Hz step','250 Hz curvature'],
           ylabel='Accepted controls / 3 trials',ylim=(0,3.6));ax.legend(fontsize=8)
    ax.set_title('Known-origin controls through candidate search, covariance estimation and paired position fitting')
    fig.savefig(out/'stress_acceptance.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for j,arm in enumerate(ARMS):
        for m,label,style in zip(('production','guarded','covariance_physical'),('Production baseline','Guarded recoveries','New CH7/CH8 screen'),('-','--',':')):
            rr=[r for r in rows if r['arm']==arm and r['method']==m]
            axes[0,j].plot(range(1,9),[r['percent'] for r in rr],marker='o',ls=style,label=label)
            e=np.sort([r['error_km'] for r in rr]);axes[1,j].step(e,np.arange(1,9)/8,where='post',ls=style,label=label)
        axes[0,j].set(title=arm,xlabel='Validation scan V01–V08',ylabel='GLRT associated (%)',xticks=range(1,9));axes[0,j].legend(fontsize=8)
        axes[1,j].set(xlabel='Position error (km)',ylabel='Fraction of eight scans');axes[1,j].axvline(.5,color='black',lw=.7);axes[1,j].legend(fontsize=8)
    fig.suptitle('Frozen RF-selected unused panel; GPS used only after inference')
    fig.savefig(out/'panel_coverage_error.png',dpi=165);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4),layout='constrained')
    for ax,arm in zip(axes,ARMS):
        for m,label,style in zip(('production','guarded','covariance_physical'),('Production baseline','Guarded recoveries','New CH7/CH8 screen'),('-','--',':')):
            rr=[r for r in rows if r['arm']==arm and r['method']==m]
            ax.plot(range(1,9),[r['error_km'] for r in rr],marker='o',ls=style,label=label)
        ax.set(title=arm,xlabel='Validation scan V01–V08',ylabel='Position error (km)',xticks=range(1,9));ax.legend(fontsize=8)
    fig.savefig(out/'per_scan_error.png',dpi=165);plt.close(fig)
    # Plot a small accepted distortion, explicitly showing that the zero-mean
    # measurement noise is distinct from the injected systematic component.
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout='constrained')
    for col,kind in enumerate(('correct','step150','curvature250')):
        folder=stress/f'{kind}-4081';truth=read(folder/'injected_truth.json')
        v=read(folder/'covariance_physical.json');r=v['proposal']['fitted_c']
        t=np.array(r['target_times_s']);raw=np.array(r['target_raw_hz']);owners=np.array(r['target_owners'])
        for lane,ax in enumerate(axes[:,col]):
            use=owners==lane;bias=r['physical_target_checks'][lane]['bias_hz']
            ax.plot(t[use],raw[use]-bias,'.-',ms=4,label=f'CH{7+lane} residual')
            ax.axhline(0,color='black',lw=.7);ax.legend(fontsize=8)
            ax.set(xlabel='Time (s)',ylabel='Residual after offset (Hz)',title=f'{kind}: accepted={v["accepted"]}')
    fig.suptitle('Residual-screen power at modest distortions; seed 4081')
    fig.savefig(out/'stress_residuals.png',dpi=160);plt.close(fig)
    # Explain test power without changing the frozen acceptance policy.
    from leo.analysis.research.covariance_structure import prepare
    from correlated_curve_prediction import randomized_blocks
    from test_joint_high_channel_recovery import SEEDS
    diagnostic=[]
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained')
    for kind in ('correct','step150','curvature250'):
        v=read(stress/f'{kind}-4081/covariance_physical.json');r=v['proposal']['fitted_c']
        c=np.asarray(r['target_covariance_hz2']);t=np.asarray(r['target_times_s']);owners=np.asarray(r['target_owners'])
        p=prepare(c,t,owners,[randomized_blocks(t,seed=s)[0] for s in SEEDS])
        root=np.linalg.cholesky(c[np.ix_(p['order'],p['order'])])
        sim=root@np.random.default_rng(p['seed']).normal(size=(len(t),p['draws']))
        linear=np.max(abs(p['weights']@sim),axis=0)
        observed=r['target_raw_hz'];gaussian_max=float(np.max(abs(p['weights']@np.asarray(observed)[p['order']])))
        diagnostic.append(dict(kind=kind,gaussian_maximum=gaussian_max,
              gaussian_only_995_threshold=float(np.quantile(linear,.995,method='higher')),
              joint_threshold=p['threshold'],note='post-hoc diagnostic only; no changed gate or adoption'))
        if kind=='correct':
            ax.hist(linear,bins=65,density=True,alpha=.5,label='Maximum Gaussian contrast')
            ax.hist(p['simulated_maximum'],bins=65,density=True,alpha=.5,label='Including quadratic lag statistic')
            ax.axvline(p['threshold'],color='black',ls='--',label='Frozen joint threshold')
    ax.set(xlabel='Maximum statistic under known covariance',ylabel='Simulated density',
           title='A shared raw-statistic threshold reduces sensitivity of the Gaussian contrasts');ax.legend(fontsize=8)
    fig.savefig(out/'threshold_diagnostic.png',dpi=160);plt.close(fig)
    write(out/'threshold_diagnostic.json',diagnostic)
    files=[p for root in (study/'promotion-inventory-v1',panel,stress) for p in sorted(root.rglob('*.json'))]
    strings=[];index={}
    def intern(v):
        if isinstance(v,dict):return {k:intern(x) for k,x in v.items()}
        if isinstance(v,list):return [intern(x) for x in v]
        if isinstance(v,str) and v.startswith('sha256:') and len(v)==71:
            if v not in index:index[v]=len(strings);strings.append(v)
            return {'$sha256':index[v]}
        return v
    records=intern({str(p.relative_to(study)):read(p) for p in files})
    with gzip.GzipFile(filename=str(out/'receipts.json.gz'),mode='wb',mtime=0) as gz:
        gz.write(json.dumps(dict(sha256_strings=strings,records=records),separators=(',',':'),allow_nan=False).encode())
    write(out/'provenance.json',dict(inputs={str(p.relative_to(study)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
          report_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(dict(stats=stats,decisions=decisions),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
