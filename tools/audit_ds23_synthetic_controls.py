"""Summarize bounded synthetic controls, keeping solver and gate success distinct."""

from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from run_algo01_ds23_sample import ROOT,read,write,sha
from probe_ds23_synthetic_noise import gate_counts


def main():
    zero=ROOT/'reports/2026_10_20_ds23_synthetic_closure'
    noise=ROOT/'reports/2026_10_20_ds23_synthetic_noise'
    rows=[];bindings={}
    for directory,condition in [(zero,'No random noise'),(noise,'Declared Gaussian noise')]:
        protocol=read(directory/'protocol.json')
        sources=protocol['source_sha256']
        if isinstance(sources,str):sources={'probe_ds23_synthetic_closure.py':sources}
        for name,expected in sources.items():
            if sha(ROOT/'tools'/name)!=expected:raise ValueError('synthetic control implementation changed')
        for path in sorted(directory.glob('DS23-*.json')):
            record=read(path);bindings[str(path.relative_to(ROOT))]=sha(path)
            if record['status']!='complete':raise ValueError('incomplete control cannot be silently excluded')
            key='source_observations_unchanged' if directory==noise else 'original_observations_unchanged'
            if not record[key]:raise ValueError('real observations changed')
            for arm,saved in record['arms'].items():
                if saved['linear_calibration_max_difference']!=0:raise ValueError('predictive data altered calibration')
                counts=gate_counts(saved)
                rows.append(dict(case=record['case'],condition=condition,arm=arm,
                    instance=record.get('draw',record.get('site_index')),error_km=saved['synthetic_position_error_km'],
                    RMS_hz=saved['RMS_hz'],**counts))
    summary={}
    for condition in ('No random noise','Declared Gaussian noise'):
        summary[condition]={}
        for arm in ('c0','fitted_c'):
            selected=[r for r in rows if r['condition']==condition and r['arm']==arm]
            summary[condition][arm]=dict(n=len(selected),mean_error_km=float(np.mean([r['error_km'] for r in selected])),
                median_error_km=float(np.median([r['error_km'] for r in selected])),maximum_error_km=max(r['error_km'] for r in selected),
                all_gate_qualified=sum(r['all_original_gates_pass'] for r in selected),
                failed_curved=sum(r['failed_curved'] for r in selected),failed_predictive=sum(r['failed_predictive'] for r in selected))
    figure,axes=plt.subplots(1,3,figsize=(14,4.6))
    conditions=('No random noise','Declared Gaussian noise');colors={'c0':'#197c91','fitted_c':'#c44c31'}
    for axis,case in zip(axes[:2],('DS23-0001','DS23-0002'),strict=True):
        for arm,offset in [('c0',-.07),('fitted_c',.07)]:
            for k,condition in enumerate(conditions):
                values=[r['error_km'] for r in rows if r['case']==case and r['condition']==condition and r['arm']==arm]
                axis.scatter(k+offset+np.linspace(-.025,.025,len(values)),values,color=colors[arm],s=28,label=arm if k==0 else None)
        axis.axhline(.5,ls='--',color='black',lw=.8)
        axis.set(xticks=[0,1],xticklabels=['No noise','Declared noise'],yscale='log',ylabel='Synthetic position error (km)',title=case,ylim=(.0005,1))
        axis.grid(alpha=.2);axis.legend(fontsize=8)
    for arm,offset in [('c0',-.16),('fitted_c',.16)]:
        vals=[summary[c][arm]['all_gate_qualified']/summary[c][arm]['n']*100 for c in conditions]
        axes[2].bar(np.arange(2)+offset,vals,width=.28,color=colors[arm],label=arm)
    axes[2].set(xticks=[0,1],xticklabels=['No noise (6)','Noise (8)'],ylabel='Instances passing all original gates (%)',ylim=(0,110),title='Qualification differs from solver accuracy')
    axes[2].legend(fontsize=8);axes[2].grid(axis='y',alpha=.2)
    figure.suptitle('Known-label synthetic controls · two templates · real evaluation GPS never read\nZero noise: three synthetic sites; noise: four draws/template at a fixed synthetic site; zero nuisance coefficients')
    figure.tight_layout();figure.savefig(noise/'synthetic_control_diagnostics.png',dpi=170);plt.close(figure)
    write(noise/'independent_control_audit.json',dict(summary=summary,bindings=bindings,
        audit_source_sha256=sha(Path(__file__)),all_completed_instances_included=True,
        oracle_labels_and_zero_nuisance_coefficients=True,not_full_hierarchical_prior_predictive=True,
        zero_noise_gate_failures_not_hidden=True,no_real_data_accuracy_improvement_claim=True,
        next_diagnostic='Draw radio, smooth, orbit and per-fragment nuisance coefficients separately at their causal prior scales, with paired noise realizations, before attributing real-data error to wrong labels.'))
    print(summary,flush=True)


if __name__=='__main__':main()
