"""Saved-array reports only; no propagation, inference or noise estimation."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
RUN=HERE/'run02';OUT=HERE/'report02'
ARMS=('c0','fitted_c');FOLDS=('early_to_late','late_to_early');MODELS=('nominal','three_modes')


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def encode(x):return x.tolist() if isinstance(x,np.ndarray) else x.item() if isinstance(x,np.generic) else str(x)
def dump(path,value):path.write_text(json.dumps(value,indent=2,default=encode)+'\n')


def write_csv(path,rows):
    keys=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys);writer.writeheader();writer.writerows(rows)


def main():
    if OUT.exists():raise FileExistsError('Report is immutable; use a separately versioned correction')
    for path,expected in read(RUN/'RF_seal.json')['files'].items():
        if sha(Path(path))!=expected:raise ValueError('RF-sealed artifact changed: '+path)
    OUT.mkdir();rows=[];points=[];models={};pairs=[]
    for arm in ARMS:
        inputs=dict(np.load(RUN/(arm+'_input.npz')))
        for fold in FOLDS:
            pair=[]
            for model in MODELS:
                name=arm+'_'+fold+'_'+model;path=RUN/(name+'_result.json')
                if not path.exists():
                    rows.append(dict(arm=arm,fold=fold,model=model,status='unavailable'));continue
                result=read(path);v=result['orders']['64'];a=dict(np.load(RUN/(name+'_GL64.npz')))
                models[(arm,fold,model)]=(result,v,a,inputs)
                row=dict(arm=arm,fold=fold,model=model,status=result['status'],numeric_stability_passed=result['numerically_qualified'],
                    train_count=len(result['train_indices']),held_count=len(result['held_indices']),
                    held_negative_twice_log_density=v['held_negative_twice_log_density'],held_RMS_Hz=v['raw_RMS_Hz'],
                    maximum_absolute_marginal_z=v['maximum_absolute_predictive_z'],
                    train_phase_mean_s=v['phase_mean_s'],train_phase_SD_s=v['phase_SD_s'],
                    train_constant_mean_Hz=v['source_constant_mean_Hz'],alias_edge_mass=v['alias_edge_mass'],
                    joint_conditional_identity_error=v['joint_conditional_identity_error'])
                for i,value in enumerate(v['shape_mean'],1):row['physical_mode_'+str(i)+'_mean']=value
                rows.append(row);pair.append(row)
                for i,index in enumerate(result['held_indices']):
                    points.append(dict(arm=arm,fold=fold,model=model,native_id=str(inputs['native_ids'][index]),
                        time_s=inputs['times'][index],radio_conditioned_observed_Hz=inputs['raw'][index],
                        predicted_mean_Hz=a['prediction_mean'][i],model_moment_SD_Hz=a['prediction_SD'][i],
                        residual_Hz=a['held_raw_residual'][i],marginal_z=a['held_raw_residual'][i]/a['prediction_SD'][i]))
            if len(pair)==2:
                pairs.append(dict(arm=arm,fold=fold,held_count=pair[0]['held_count'],
                    three_minus_nominal_negative_twice_log_density=pair[1]['held_negative_twice_log_density']-pair[0]['held_negative_twice_log_density'],
                    nominal_RMS_Hz=pair[0]['held_RMS_Hz'],three_mode_RMS_Hz=pair[1]['held_RMS_Hz'],
                    nominal_maximum_absolute_marginal_z=pair[0]['maximum_absolute_marginal_z']))
    write_csv(OUT/'diagnostics.csv',rows);write_csv(OUT/'per_point.csv',points);write_csv(OUT/'paired_comparisons.csv',pairs)
    noise={}
    for arm in ARMS:
        source=RUN/(arm+'_noise.json');full=read(source)
        noise[arm]=dict({key:val for key,val in full.items() if key!='per_observation_noise_sigma_hz'},
            full_source=str(source),full_source_sha256=sha(source))
    dump(OUT/'noise_summary.json',noise)
    execution=read(RUN/'execution.json')
    summary=dict(complete_model_slots=sum(r['status']=='complete' for r in rows),declared_model_slots=8,
        numerically_stable_slots=sum(bool(r.get('numeric_stability_passed')) for r in rows),
        paired_comparisons=pairs,rows=rows,execution=execution,
        measured_known_worker_seconds=execution['cumulative_worker_seconds']-90.,
        failed_setup_elapsed_unknown_charged_bound_seconds=90.,
        one_owner_not_independent_replicates=True,identity_admissions=0,position_fits=0,
        moment_bands_not_calibrated_95percent_intervals=True)
    dump(OUT/'summary.json',summary)

    colors={'nominal':'#0072B2','three_modes':'#D55E00'}
    labels={'nominal':'Nominal','three_modes':'Three physical modes'}
    fig,axes=plt.subplots(2,2,figsize=(13,8),constrained_layout=True)
    for i,arm in enumerate(ARMS):
        for j,fold in enumerate(FOLDS):
            ax=axes[i,j];available=False
            for model in MODELS:
                item=models.get((arm,fold,model))
                if item is None:continue
                available=True;result,v,a,inputs=item;held=np.asarray(result['held_indices']);train=np.asarray(result['train_indices'])
                times=inputs['times'][held]
                ax.plot(times,a['held_raw_residual'],'o-',ms=3,color=colors[model],label=labels[model]+' held residual')
                ax.fill_between(times,-2*a['prediction_SD'],2*a['prediction_SD'],alpha=.10,color=colors[model],
                                label=labels[model]+' moment ±2 SD')
            if not available:
                ax.text(.5,.5,'Unavailable',ha='center',transform=ax.transAxes);continue
            ax.axvspan(float(inputs['times'][train].min()),float(inputs['times'][train].max()),color='.9',zorder=-3)
            ax.text(float(inputs['times'][train].mean()),.98,'Train only\n(not scored)',ha='center',va='top',fontsize=8,
                    transform=ax.get_xaxis_transform())
            ax.axhline(0,color='.4',lw=.8);ax.grid(alpha=.2)
            name='Early 14 → late 15' if fold=='early_to_late' else 'Late 15 → early 14'
            ax.set_title(('c = 0' if arm=='c0' else 'Fitted c')+': '+name)
            ax.set_xlabel('Scan time (s)');ax.set_ylabel('Held observation − train-only forecast (Hz)')
            ax.legend(fontsize=7,loc='lower left')
    fig.suptitle('Offline conditional prediction within one exposed owner\nBands show mixture moments ±2 SD, not calibrated 95% intervals; all 29 points remain across folds',fontsize=13)
    fig.savefig(OUT/'chronological_forecasts.png',dpi=170);fig.savefig(OUT/'chronological_forecasts.pdf');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    x=np.arange(len(pairs));names=[('c0' if q['arm']=='c0' else 'Fitted c')+'\n'+('Early→late' if q['fold']=='early_to_late' else 'Late→early') for q in pairs]
    difference=[q['three_minus_nominal_negative_twice_log_density'] for q in pairs]
    axes[0].bar(x,difference,color=['#0072B2' if q['arm']=='c0' else '#D55E00' for q in pairs])
    for i,value in enumerate(difference):axes[0].text(i,value-.15,f'{value:.2f}',ha='center',va='top',fontsize=9)
    axes[0].set_ylim(min(difference)-1,0.5);axes[0].axhline(0,color='.4',lw=.8)
    axes[0].set_ylabel('Three-mode − nominal held −2 log density\nLower favors three modes');axes[0].set_title('Proper conditional score, direction by direction')
    means=[models[(q['arm'],q['fold'],'three_modes')][1]['shape_mean'][0] for q in pairs]
    axes[1].bar(x,means,color=['#0072B2' if q['arm']=='c0' else '#D55E00' for q in pairs])
    axes[1].axhline(0,color='.4',lw=.8);axes[1].set_ylabel('Train-only physical mode 1 mean\n(unit prior coordinates)');axes[1].set_title('Training directions infer different pulls')
    for ax in axes:ax.set_xticks(x,names);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Four conditional comparisons reuse ONE exposed owner\nNo combined significance, identity qualification or position accuracy claim',fontsize=13)
    fig.savefig(OUT/'paired_scores.png',dpi=170);fig.savefig(OUT/'paired_scores.pdf');plt.close(fig)
    dump(OUT/'seal.json',dict(RF_seal_sha256=sha(RUN/'RF_seal.json'),source_sha256=sha(Path(__file__)),
        saved_arrays_only=True,files={str(path.relative_to(HERE)):sha(path) for path in sorted(OUT.iterdir()) if path.is_file()}))
    print('REPORT_READY',len(rows),len(points),len(pairs))


if __name__=='__main__':main()
