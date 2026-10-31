"""Render fixed family-heldout diagnostics without fitting any further model."""
import argparse,csv,hashlib,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def pool(evals,key):
    return float(np.sqrt(sum(e['before']['points']*e[key]['RMS_hz']**2 for e in evals)/sum(e['before']['points'] for e in evals)))


def writecsv(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def run(base):
    data=json.loads((base/'result.json').read_text());targets=[];families=[];bands=[]
    fig,axes=plt.subplots(3,2,figsize=(15,11),sharex=True,sharey=True,layout='constrained')
    for f in data['folds']:
        e=next(e for e in f['evaluations'] if e['target']);t=np.asarray(e['times_s']);fc=e['forecast'];ok=np.asarray(fc['support'])
        ax=axes[f['fold'],['c0','fitted_c'].index(f['arm'])]
        ax.plot(t,e['before']['residual_hz'],'k.-',lw=.8,ms=3,label='Target before')
        ax.plot(t,e['after']['residual_hz'],'.-',c='#2878b5',lw=.8,ms=3,label='Target after')
        prediction=np.asarray(fc['prediction_hz']);sd=np.asarray(fc['correction_sigma_hz'])
        ax.plot(t,prediction,c='#df8700',lw=1.4,label='Applied witness prediction')
        ax.fill_between(t,prediction-1.96*sd,prediction+1.96*sd,where=ok,color='#df8700',alpha=.2,label='Correction-only conditional 95%')
        ax.scatter(t[~ok],np.full(sum(~ok),-800.),marker='x',s=14,c='.55',label='Unsupported; correction zero')
        ax.axhline(0,c='.5',lw=.5);ax.grid(alpha=.2)
        ax.set_title(f"Fold {f['fold']} / {f['arm']} / support {sum(ok)}/{len(ok)}\nRMS {e['before']['RMS_hz']:.1f} → {e['after']['RMS_hz']:.1f} Hz; fails {', '.join(e['after']['failed_gates'])}",fontsize=10)
        ax.set_ylim(-850,1100)
        if f['fold']==2:ax.set_xlabel('Device time (s)')
        if f['arm']=='c0':ax.set_ylabel('Residual / prediction (Hz)')
        targets.append(dict(fold=f['fold'],arm=f['arm'],held_families=' '.join(map(str,f['held_families'])),
          training_east_km=f['training']['endpoint_east_north_km'][0],training_north_km=f['training']['endpoint_east_north_km'][1],
          before_RMS_hz=e['before']['RMS_hz'],after_RMS_hz=e['after']['RMS_hz'],
          failed_gates=','.join(e['after']['failed_gates']),lag1_acf=e['after']['noise']['lag1_acf'],
          supported_points=int(sum(ok)),total_points=len(ok),supported_after_RMS_hz=e['supported_after'].get('RMS_hz'),
          supported_failed_gates=','.join(e['supported_after'].get('failed_gates',[])) if sum(ok)>=4 else 'insufficient_points',
          median_correction_sigma_hz=float(np.median(sd)),median_total_sigma_hz=e['after']['median_predictive_sigma_hz'],
          approximate_95_coverage=e['after']['approximate_marginal_95_coverage'],
          final_phase_change_s=f['training']['final_phase_change_s'],fit_seconds=f['seconds']))
        for n in f['held_families']+[data['protocol']['target_family']]:
            members=[q for q in f['evaluations'] if q['norad']==n]
            if not members:continue
            npoints=sum(q['after']['points'] for q in members);supported=sum(sum(q['forecast']['support']) for q in members)
            families.append(dict(fold=f['fold'],arm=f['arm'],norad=n,target_family=n==data['protocol']['target_family'],
              tracks=len(members),points=npoints,supported_points=int(supported),before_RMS_hz=pool(members,'before'),after_RMS_hz=pool(members,'after'),
              worsened_tracks=sum(q['after']['RMS_hz']>q['before']['RMS_hz'] for q in members),
              passing_tracks=sum(not q['after']['failed_gates'] for q in members)))
        for rx in (1,2):
          for band in (0,1):
            members=[q for q in f['evaluations'] if q['norad'] in f['held_families'] and q['receiver']==rx and int(q['channel']>4)==band]
            if members:bands.append(dict(fold=f['fold'],arm=f['arm'],receiver=rx,band='upper' if band else 'lower',tracks=len(members),
              before_RMS_hz=pool(members,'before'),after_RMS_hz=pool(members,'after'),
              supported_points=int(sum(sum(q['forecast']['support']) for q in members)),
              total_points=sum(q['after']['points'] for q in members)))
    axes[0,0].legend(fontsize=8,loc='lower left')
    fig.suptitle('DS26-0050 — whole-family holdout; all NORAD63468 evidence excluded from training\nFixed6s/150Hz model; common regional cold start; zero correction without two nearby training families; unchanged gates',fontsize=13)
    fig.savefig(base/'target-before-after.png',dpi=160);fig.savefig(base/'target-before-after.pdf');plt.close(fig)
    writecsv(base/'target-summary.csv',targets);writecsv(base/'held-family-summary.csv',families);writecsv(base/'receiver-band-summary.csv',bands)
    fig,axes=plt.subplots(3,2,figsize=(14,10),layout='constrained')
    for fold in range(3):
      for ci,arm in enumerate(('c0','fitted_c')):
        rows=[r for r in families if r['fold']==fold and r['arm']==arm and not r['target_family']]
        ax=axes[fold,ci];x=np.arange(len(rows));before=[r['before_RMS_hz'] for r in rows];after=[r['after_RMS_hz'] for r in rows]
        ax.bar(x-.18,before,.36,label='Before',color='.4');ax.bar(x+.18,after,.36,label='After',color='#2878b5')
        ax.set_xticks(x,[str(r['norad']) for r in rows],fontsize=8);ax.set_yscale('log');ax.grid(axis='y',alpha=.2)
        ax.set_title(f'Fold {fold} / {arm} — complete held families');ax.set_ylabel('Pooled residual RMS (Hz, log)')
    axes[0,0].legend();fig.suptitle('Independent held-family regressions; original conditional candidate/alias nominations')
    fig.savefig(base/'held-families.png',dpi=150);fig.savefig(base/'held-families.pdf');plt.close(fig)
    src=Path(__file__).parent
    paths=list(src.glob('*.py'))+[Path('/srv/bulk/leo-dev/fast-algo02-production-v1/tools')/s for s in
      ('annotate_track_predictively.py','diagnose_all_large_tracks.py','ds23_predictive_linear.py','investigate_ds23_0268_remaining_tracks.py')]
    manifest=dict(data['protocol']['source_sha256']);manifest.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    (base/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(targets=targets,held_families=families,receiver_band=bands),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);run(p.parse_args().base)
