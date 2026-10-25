"""Small reporting pass on frozen direct-measurement contrasts; no inference."""

import csv
import os
from pathlib import Path

import numpy as np

os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parent/'.mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import contrasts as c

METHODS=('zero','native','reversed_polarity','shift75','prior_only')
LABELS={'zero':'Zero / affine only','native':'Native training','reversed_polarity':'Reversed training polarity',
        'shift75':'Circular75s training shift','prior_only':'Untrained prior covariance'}
COLORS={'zero':'0.35','native':'#0072B2','reversed_polarity':'#CC79A7','shift75':'#D55E00','prior_only':'#009E73'}
HERE=c.HERE
FIG=HERE/'figures'


def read_csv(path):
    with path.open() as stream:
        return list(csv.DictReader(stream))


def save(fig,name,caption):
    fig.text(.5,.015,caption,ha='center',va='bottom',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.95))
    for suffix in ('.png','.pdf'):
        fig.savefig(FIG/(name+suffix),dpi=170)
    plt.close(fig)


def aggregate(rows):
    points=sum(int(v['points'] if 'points' in v else v['native_time_points']) for v in rows)
    dimension=sum(int(v['dimension']) for v in rows)
    square=sum(float(v.get('projected_native_time_square_hz2',v.get('projected_native_time_mean_square_hz2'))) for v in rows)
    return dict(points=points,dimension=dimension,gain=sum(float(v.get('gain',v.get('gain_vs_zero'))) for v in rows),
        projected_native_time_RMS_hz=float(np.sqrt(square/points)),
        standardized_RMS=float(np.sqrt(sum(float(v.get('standardized_square',v.get('standardized_mean_square'))) for v in rows)/dimension)))


def main():
    seal=c.read(HERE/'scientific_seal.json')
    for name,digest in seal['files'].items():
        assert c.sha(HERE/name)==digest,name
    protocol=c.read(HERE/'protocol.json');cases=protocol['cases']
    case_scores=read_csv(HERE/'case_scores.csv')
    family_scores=read_csv(HERE/'family_scores.csv')
    support=read_csv(HERE/'support.csv')
    summary=[]
    for variant in ('measurement','nominal_curvature_sensitivity'):
        for method in METHODS:
            rows=[v for v in case_scores if v['variant']==variant and v['method']==method]
            summary.append(dict(variant=variant,method=method,scans=len(rows),positive_scan_density_gain=sum(float(v['gain'])>0 for v in rows),**aggregate(rows)))
    c.csv_write(HERE/'pooled_method_summary.csv',summary)
    by_key={(r['case'],r['norad'],r['method']):r for r in family_scores if r['variant']=='measurement'}
    strata=[]
    for label in ('none','partial','all'):
        selected=[r for r in family_scores if r['variant']=='measurement' and r['method']=='native' and
            ('none' if float(r['held_time_with_training_within_5s_fraction'])==0 else 'all' if float(r['held_time_with_training_within_5s_fraction'])==1 else 'partial')==label]
        for method in METHODS:
            rows=[by_key[(r['case'],r['norad'],method)] for r in selected]
            if rows:
                strata.append(dict(training_time_coverage=label,method=method,family_blocks=len(rows),**aggregate(rows)))
    c.csv_write(HERE/'time_coverage_strata.csv',strata)
    native=[r for r in family_scores if r['variant']=='measurement' and r['method']=='native']
    improvements=sum(float(v['projected_native_time_mean_square_hz2'])<float(by_key[(v['case'],v['norad'],'zero')]['projected_native_time_mean_square_hz2']) for v in native)
    primary=[v for v in summary if v['variant']=='measurement']
    result=dict(all_24_retained=True,primary=primary,curvature_sensitivity=[v for v in summary if v['variant']!='measurement'],
        native_mean_RMS_improving_family_blocks=improvements,total_family_blocks=len(native),
        native_mean_RMS_improving_scans=sum(float(v['projected_native_time_square_hz2'])<float(next(z for z in case_scores if z['variant']=='measurement' and z['method']=='zero' and z['case']==v['case'])['projected_native_time_square_hz2']) for v in case_scores if v['variant']=='measurement' and v['method']=='native'),
        held_family_training_within5s_coverage_median=float(np.median([float(v['held_time_with_training_within_5s_fraction']) for v in native])),
        held_family_no_training_within5s=sum(float(v['held_time_with_training_within_5s_fraction'])==0 for v in native),
        maximum_nominal_interpolation_envelope_hz=max(float(v['max_nominal_interpolation_envelope_hz']) for v in support),
        maximum_interpolation_gap_s=max(float(v['max_interpolation_gap_s']) for v in support),
        full_interpolation_nonzero_offdiagonal_count=sum(int(v['offdiagonal_interpolation_covariance_count']) for v in support),
        no_position_fits_or_GPS=True,not_an_absolute_receiver_or_position_calibration=True)
    c.write(HERE/'report_summary.json',result)
    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({'font.size':10})
    fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
    counts=[sum(r['case']==case for r in support) for case in cases]
    points=[sum(int(r['unique_RX1_points']) for r in support if r['case']==case) for case in cases]
    axes[0].bar(range(24),counts,color='#0072B2');axes[0].set_ylabel('Paired curved families')
    twin=axes[0].twinx();twin.plot(range(24),points,'.-',color='#D55E00');twin.set_ylabel('Unique RX1 anchor points',color='#D55E00')
    for i,case in enumerate(cases):
        fractions=[float(r['held_time_with_training_within_5s_fraction']) for r in native if r['case']==case]
        axes[1].scatter(np.full(len(fractions),i),fractions,color='0.35',s=18,alpha=.7)
        axes[1].plot(i,np.median(fractions),'_',color='#D55E00',markersize=15,markeredgewidth=2)
    axes[1].set(ylabel='Held times with another family within5s',ylim=(-.05,1.05))
    axes[1].set_xticks(range(24),[v.split('-')[1] for v in cases],rotation=55)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.suptitle('Direct same-channel receiver contrasts exist in all24 scans, with incomplete time overlap')
    save(fig,'support_and_time_coverage','Families/points are inherited accepted-curved evidence; no new identity or association is qualified.\nOrange marks in lower panel show median coverage;42/154 families have no other-family point within5s.')

    fig,axes=plt.subplots(2,1,figsize=(14,9),sharex=True)
    for j,method in enumerate(METHODS[1:]):
        rows=[next(v for v in case_scores if v['case']==case and v['variant']=='measurement' and v['method']==method) for case in cases]
        axes[0].bar(np.arange(24)+(j-1.5)*.2,[float(v['gain']) for v in rows],width=.2,color=COLORS[method],label=LABELS[method])
        change=[]
        for case,row in zip(cases,rows,strict=True):
            zero=next(v for v in case_scores if v['case']==case and v['variant']=='measurement' and v['method']=='zero')
            change.append(np.sqrt(float(row['projected_native_time_square_hz2'])/int(row['points']))-np.sqrt(float(zero['projected_native_time_square_hz2'])/int(zero['points'])))
        axes[1].plot(range(24),change,'.-',color=COLORS[method],label=LABELS[method])
    axes[0].set_ylabel('Held density gain vs zero (positive better)');axes[0].legend(ncol=2,fontsize=9)
    axes[1].set_ylabel('Projected differential RMS change (Hz)')
    axes[1].set_xticks(range(24),[v.split('-')[1] for v in cases],rotation=55)
    for ax in axes:ax.axhline(0,color='0.3',lw=.8);ax.grid(axis='y',alpha=.2)
    fig.suptitle('Direct cross-family receiver prediction has a small, heterogeneous mean gain')
    save(fig,'prediction_and_controls','Same held affine-null vector, complete Gaussian covariance and normalization for every predictor.\nWhole-family leave-outs overlap in training; summed gains are diagnostics, not independent significance or hardware evidence.')

    fig,axes=plt.subplots(1,2,figsize=(12,6))
    observed=[];forecast=[];coverage=[];gains=[]
    for row in native:
        base=by_key[(row['case'],row['norad'],'zero')]
        observed.append(np.sqrt(float(base['projected_native_time_mean_square_hz2'])/int(base['native_time_points'])))
        forecast.append(np.sqrt(float(row['projected_native_time_mean_square_hz2'])/int(row['native_time_points'])))
        coverage.append(float(row['held_time_with_training_within_5s_fraction']));gains.append(float(row['gain_vs_zero']))
    scatter=axes[0].scatter(observed,forecast,c=coverage,vmin=0,vmax=1,cmap='viridis',s=25)
    end=max(max(observed),max(forecast));axes[0].plot([0,end],[0,end],'--',color='0.4')
    axes[0].set(xlabel='Zero-mean projected differential RMS (Hz)',ylabel='Native-predicted RMS (Hz)')
    axes[1].scatter(coverage,gains,c=coverage,vmin=0,vmax=1,cmap='viridis',s=25)
    axes[1].axhline(0,color='0.4',lw=.8);axes[1].set(xlabel='Held-time coverage by training families within5s',ylabel='Native held density gain')
    for ax in axes:ax.grid(alpha=.2)
    fig.colorbar(scatter,ax=axes[1],label='Time coverage')
    fig.suptitle('Family outcomes remain mixed and many targets lack simultaneous training support')
    save(fig,'family_prediction_and_overlap','Each point is one conditional family/scan target. Native-time RMS reconstructs the noise-weighted affine-null vector.\nSame NORAD/RF does not exclude distinct nonlinear transmitter/path errors; labels and noise were selected from earlier all-RF data.')

    fig,axes=plt.subplots(2,2,figsize=(13,8))
    for column,case in enumerate(cases[:2]):
        rows=read_csv(HERE/'cases'/(case+'_native_time_contrasts.csv'))
        norads=sorted({int(v['norad']) for v in rows})[:2]
        for ax,norad in zip(axes[:,column],norads,strict=True):
            for method in ('zero','native','shift75'):
                selected=[v for v in rows if int(v['norad'])==norad and v['method']==method]
                for pair in sorted({int(v['pair']) for v in selected}):
                    series=sorted((v for v in selected if int(v['pair'])==pair),key=lambda v:float(v['time_s']))
                    t=[float(v['time_s']) for v in series]
                    if method=='zero':
                        ax.scatter(t,[float(v['projected_differential_hz']) for v in series],s=13,color='0.4',alpha=.7,label='Observed contrast' if pair==0 else None)
                    else:
                        ax.plot(t,[float(v['predicted_differential_hz']) for v in series],color=COLORS[method],lw=1.5,
                            label=LABELS[method] if pair==0 else None)
            ax.axhline(0,color='0.7',lw=.7);ax.set(title=f'{case} / inherited family{norad}',xlabel='Scan time (s)',ylabel='Projected RX1-RX2 at11.5GHz (Hz)');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Metadata-chosen examples: first two families in the first two chronological scans')
    save(fig,'chronological_examples','Separate lines retain distinct source-pair affine projections. They are held-family differential mean predictions, not CFO residuals or position fits.\nThe relative receiver contrast cannot identify which receiver is wrong or determine absolute localization precision.')
    files={str(p.relative_to(HERE)):c.sha(p) for p in sorted(FIG.iterdir())}
    c.write(HERE/'report_seal.json',dict(report_source_sha256=c.sha(Path(__file__)),scientific_seal_sha256=c.sha(HERE/'scientific_seal.json'),figures=files,
        derived_files={name:c.sha(HERE/name) for name in ('report_summary.json','pooled_method_summary.csv','time_coverage_strata.csv')}))
    print(result)


if __name__=='__main__':
    main()
