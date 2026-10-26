"""Saved-array owner/coverage diagnostics; no geometry or fitting."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
OWN=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/transfer/ownership')
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    out=HERE/'details';out.mkdir(exist_ok=False);owners=[];losses=[]
    protocol=read(HERE/'protocol.json');corrections=read(ROOT/'measurement/corrections.json')['rows']
    for case in protocol['cases']:
        original=read(SOURCE/'family_cavity/position'/(case+'.json'))
        node=original['selected']['node'] if original['accepted'] else original['baseline_node']
        curve_rows=[r for r in node['seed']['rows'] if r['active_curvature']]
        tracks={t['key']:t for t in read(SOURCE/case/'tracks.json')}
        boundaries=np.r_[0,np.cumsum([len(tracks[r['component']]['times']) for r in curve_rows])]
        for arm in protocol['arms']:
            a=read(HERE/case/'original'/arm/'raw_endpoint.json');b=read(HERE/case/'corrected'/arm/'raw_endpoint.json')
            if len(a['noise_precision'])!=len(curve_rows):raise ValueError('saved native coefficient ordering differs')
            for index,row in enumerate(curve_rows):
                key=row['component']
                if key not in protocol['selected'][case]['owners']:continue
                ix=slice(boundaries[index],boundaries[index+1]);rr=[r for r in corrections if r['case']==case and r['complete_owner']==key]
                delta=np.array([r['corrected_cfo_hz']-r['original_cfo_hz'] for r in rr])
                if len(rr)!=len(tracks[key]['times']):raise ValueError('complete owner count differs')
                owners.append(dict(case=case,arm=arm,owner=key,norad=row['candidate_norad'],points=len(rr),
                    native_delta_mean_hz=float(np.mean(delta)),native_delta_RMS_hz=float(np.sqrt(np.mean(delta**2))),
                    native_delta_min_hz=float(np.min(delta)),native_delta_max_hz=float(np.max(delta)),
                    original_conditional_RMS_hz=float(np.sqrt(np.mean(np.asarray(a['conditional_residual_hz'])[ix]**2))),
                    corrected_conditional_RMS_hz=float(np.sqrt(np.mean(np.asarray(b['conditional_residual_hz'])[ix]**2))),
                    original_Gamma_precision=a['noise_precision'][index],corrected_Gamma_precision=b['noise_precision'][index],
                    Gamma_precision_ratio=b['noise_precision'][index]/a['noise_precision'][index]))
            gates=read(HERE/case/'corrected'/arm/'gates.json');lost=set(gates['original_accepted_IDs_lost'])
            base=read(OWN/case/'parent.json')['coverage'][arm]
            for row in base['associations']:
                ids=sorted(lost&set(row['observation_ids']))
                if not ids:continue
                if set(ids)&set(base['curved_observation_ids']+base['predictive_observation_ids']):raise ValueError('loss includes fitted evidence')
                losses.append(dict(case=case,arm=arm,owner=row['component'],norad=row.get('norad'),lost_native_IDs=ids,
                    role='postfit_only',directly_corrected=False,original_native_RMS_hz=row.get('native_rms_hz'),
                    original_profile_bias_hz=row.get('bias_hz'),
                    new_rejected_extension_predicates='not retained by original accepted-only extension output',
                    all_fitted_likelihood_IDs_unchanged=True))
    with (out/'owner_diagnostics.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(owners[0]));writer.writeheader();writer.writerows(owners)
    with (out/'postfit_losses.json').open('x') as f:json.dump(losses,f,indent=2);f.write('\n')
    rf=read(HERE/'rf_report/summary.json')['contrasts'];geo=read(HERE/'geographic/summary.json')['paired']
    fig,axes=plt.subplots(1,2,figsize=(10,4.4),layout='constrained')
    x=np.arange(4);labels=[r['case']+'\n'+('c=0' if r['arm']=='c0' else 'fitted c') for r in rf]
    rms=[r['conditional_RMS_difference_hz'] for r in rf]
    gain=[next(g for g in geo if g['case']==r['case'] and g['arm']==r['arm'])['raw_gain_m'] for r in rf]
    for ax,y,title,unit in zip(axes,(rms,gain),('Frequency residuals increase','Raw geographic errors decrease'),('Conditional RMS change (Hz)','Original − corrected error (m)')):
        bars=ax.bar(x,y,color=['#176b8b','#176b8b','#a9652a','#a9652a']);ax.bar_label(bars,fmt='%.2f',padding=3)
        ax.set_xticks(x,labels,fontsize=8);ax.set_title(title);ax.set_ylabel(unit);ax.axhline(0,color='.3',lw=.7);ax.grid(axis='y',alpha=.2)
        ax.set_ylim(0,max(y)*1.2)
    fig.suptitle('Measurement precision, model residuals and position accuracy are distinct\nDS24-0011 remains paired-unqualified because of postfit-only ID loss',fontsize=11)
    fig.savefig(out/'RF_and_position.png',dpi=180);plt.close(fig)
    paths=[Path(__file__),out/'owner_diagnostics.csv',out/'postfit_losses.json',out/'RF_and_position.png',
           HERE/'RF_seal.json',HERE/'rf_report/seal.json',HERE/'geographic/seal.json',ROOT/'measurement/corrections.json']
    with (out/'seal.json').open('x') as f:json.dump(dict(files={str(p):sha(p) for p in paths}),f,indent=2);f.write('\n')
    print(json.dumps(owners,indent=2))


if __name__=='__main__':main()
