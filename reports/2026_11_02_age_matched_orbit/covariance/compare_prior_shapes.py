"""Read-only comparison of sealed oldB/Age2 prior receipts; no RF or GPS."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parent
FIXED_CASES=['DS26-0070','DS26-0309','DS26-0044','FRSH-0004']
GAP_TOLERANCE=1e-6


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def description(coefficients,covariance):
    a=np.asarray(coefficients,float);c=np.asarray(covariance,float)
    s=a.T@a/len(a);mean=a.mean(axis=0)
    eig,vectors=np.linalg.eigh(c);raw_eig,raw_vectors=np.linalg.eigh(s)
    # Uncentered second moment = centered covariance + squared signed mean.
    fraction=float(mean@mean/max(float(np.trace(s)),1e-30))
    assert -1e-10<=fraction<=1+1e-10
    assert np.allclose(s,(a-mean).T@(a-mean)/len(a)+np.outer(mean,mean),atol=1e-10)
    values,axes=np.linalg.eigh(.5*np.eye(3)+.5*s)
    expected=(axes*np.clip(values,1,16))@axes.T
    assert np.allclose(c,expected,atol=1e-9,rtol=0)
    covariance_gap=float((eig[-1]-eig[-2])/max(eig[-1],1e-30))
    second_gap=float((raw_eig[-1]-raw_eig[-2])/max(raw_eig[-1],1e-30))
    return dict(eigenvalues=eig.tolist(),trace=float(np.trace(c)),logdet=float(np.linalg.slogdet(c)[1]),
        signed_mean=mean.tolist(),signed_mean_energy_fraction=fraction,second_moment_trace=float(np.trace(s)),
        covariance_top_relative_eigengap=covariance_gap,second_moment_top_relative_eigengap=second_gap,
        covariance_top_direction=vectors[:,-1].tolist(),second_moment_top_direction=raw_vectors[:,-1].tolist(),
        covariance_direction_unique=covariance_gap>GAP_TOLERANCE,
        second_moment_direction_unique=second_gap>GAP_TOLERANCE)


def angle(first,second,key):
    if not first[key+'_direction_unique'] or not second[key+'_direction_unique']:return None
    dot=abs(np.asarray(first[key+'_top_direction'])@np.asarray(second[key+'_top_direction']))
    return float(np.rad2deg(np.arccos(np.clip(dot,0,1))))


def write_csv(path,rows):
    with path.open('w') as stream:
        writer=csv.DictWriter(stream,list(rows[0]));writer.writeheader();writer.writerows(rows)


def quantiles(values):
    return dict(zip(['min','median','max'],np.quantile(values,[0,.5,1]).tolist())) if values else None


def main():
    inventory_path=ROOT/'derived_inventory.json';roster_path=ROOT.parent/'evaluation/rf_roster.json'
    inventory=json.loads(inventory_path.read_text());roster=json.loads(roster_path.read_text())
    old_path=Path(roster['previous_combined_path']);old_packet=json.loads(old_path.read_text())
    assert sha(old_path)==roster['previous_combined_sha256']
    old_rows={r['case']:r for r in old_packet['rows']};records={r['case']:r for r in roster['cases']}
    new_rows={r['case']:r for r in inventory['rows']}
    ready=[r for r in inventory['rows'] if r['status']=='ready'];paired=[];excluded=[]
    for current in ready:
        case=current['case'];old=old_rows[case];prior=old.get('prior_receipt',{})
        assert old['input_sha256']==records[case]['input_sha256']
        if prior.get('status')!='ready':
            excluded.append(dict(case=case,oldB_status=prior.get('status'),reason=prior.get('reason')));continue
        assert prior['selected_family']==current['target_family']
        assert prior['nominal_element_sha256']==current['nominal_element_sha256']
        assert prior['history_sha256']==current['history_sha256']
        first=description([r['coefficients'] for r in prior['historical_projection']],prior['coefficient_covariance'])
        second=description([r['coefficients'] for r in current['historical_pair_projections']],current['coefficient_covariance'])
        rec=dict(case=case,dataset=current['dataset'],target_family=current['target_family'],
            pair_count=current['pair_count'],primary_eligible=current['pair_count']>=3,
            nominal_age_hours=current['nominal_horizon_hours'],
            age_mean_matched_horizon_hours=float(np.mean([r['horizon_hours'] for r in current['historical_pair_projections']])),
            old_mean_historical_propagation_age_hours=float(np.mean([(prior['common_epoch_utc_ns'][1]-r['epoch_utc_ns'])/3.6e12
                for r in prior['historical_projection']])),
            oldB_trace=first['trace'],Age2_trace=second['trace'],trace_ratio_Age2_over_oldB=second['trace']/first['trace'],
            oldB_logdet=first['logdet'],Age2_logdet=second['logdet'],logdet_change_Age2_minus_oldB=second['logdet']-first['logdet'],
            oldB_logvolume=.5*first['logdet'],Age2_logvolume=.5*second['logdet'],
            covariance_direction_angle_deg=angle(first,second,'covariance'),
            uncentered_second_moment_direction_angle_deg=angle(first,second,'second_moment'),
            oldB_top_relative_eigengap=first['covariance_top_relative_eigengap'],Age2_top_relative_eigengap=second['covariance_top_relative_eigengap'],
            oldB_signed_mean_energy_fraction=first['signed_mean_energy_fraction'],Age2_signed_mean_energy_fraction=second['signed_mean_energy_fraction'],
            history_sha256=current['history_sha256'],nominal_element_sha256=current['nominal_element_sha256'])
        for prefix,description_ in [('oldB',first),('Age2',second)]:
            for k in range(3):rec[prefix+'_eigenvalue_'+str(k+1)]=description_['eigenvalues'][k]
            for label,value in zip(['mean_motion','inclination','RAAN'],description_['signed_mean']):rec[prefix+'_signed_mean_'+label]=value
        paired.append(rec)
    covariance_angles=[r['covariance_direction_angle_deg'] for r in paired if r['covariance_direction_angle_deg'] is not None]
    raw_angles=[r['uncentered_second_moment_direction_angle_deg'] for r in paired if r['uncentered_second_moment_direction_angle_deg'] is not None]
    fixed=[]
    for case in FIXED_CASES:
        current=new_rows[case];prior=old_rows[case].get('prior_receipt',{})
        fixed.append(dict(case=case,oldB_status=prior.get('status'),oldB_reason=prior.get('reason'),
            Age2_status=current['status'],Age2_reason=current.get('reason'),pair_count=current.get('pair_count',0),
            nominal_age_hours=current.get('nominal_horizon_hours'),
            oldB_covariance=prior.get('coefficient_covariance') if prior.get('status')=='ready' else None,
            Age2_covariance=current.get('coefficient_covariance') if current['status']=='ready' else None))
    summary=dict(inputs={str(p):sha(p) for p in [inventory_path,roster_path,old_path,Path(__file__)]},
        no_RF_or_GPS_or_fitting=True,Age2_ready_contexts=len(ready),both_priors_ready=len(paired),
        excluded_oldB_fallbacks=excluded,primary_count_in_overlap=sum(r['primary_eligible'] for r in paired),
        trace_ratio=quantiles([r['trace_ratio_Age2_over_oldB'] for r in paired]),
        trace_decreased_count=sum(r['Age2_trace']<r['oldB_trace']-1e-10 for r in paired),
        logdet_change=quantiles([r['logdet_change_Age2_minus_oldB'] for r in paired]),
        logdet_decreased_count=sum(r['Age2_logdet']<r['oldB_logdet']-1e-10 for r in paired),
        covariance_dominant_direction=dict(unique_comparisons=len(covariance_angles),undefined_degenerate=len(paired)-len(covariance_angles),angle_deg=quantiles(covariance_angles)),
        second_moment_dominant_direction=dict(unique_comparisons=len(raw_angles),angle_deg=quantiles(raw_angles)),
        oldB_signed_mean_fraction=quantiles([r['oldB_signed_mean_energy_fraction'] for r in paired]),
        Age2_signed_mean_fraction=quantiles([r['Age2_signed_mean_energy_fraction'] for r in paired]),
        nominal_age_hours=quantiles([r['nominal_age_hours'] for r in paired]),
        matched_horizon_hours=quantiles([r['age_mean_matched_horizon_hours'] for r in paired]),
        old_historical_propagation_age_hours=quantiles([r['old_mean_historical_propagation_age_hours'] for r in paired]),
        eigengap_tolerance=GAP_TOLERANCE,fixed_cases=fixed,
        interpretation='Prior-shape diagnostics in common baseline coefficient coordinates; catalog mean fraction is not evidence of true orbit bias; degenerate dominant axes are undefined')
    write_csv(ROOT/'prior_shape_comparison.csv',paired)
    (ROOT/'prior_shape_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    plot(paired,fixed)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['inputs','fixed_cases']},indent=2))


def plot(rows,fixed):
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(13.8,4.5),layout='constrained')
    for threshold,label,color,marker in [(True,'Primary ≥3 pairs','#2878b5','s'),(False,'Exploratory 2 pairs','#36a088','o')]:
        group=[r for r in rows if r['primary_eligible']==threshold]
        for ax,x,y in [(axes[0],'oldB_trace','Age2_trace'),(axes[1],'oldB_logdet','Age2_logdet'),
                       (axes[2],'oldB_signed_mean_energy_fraction','Age2_signed_mean_energy_fraction')]:
            ax.scatter([r[x] for r in group],[r[y] for r in group],label=label,color=color,marker=marker,s=33,alpha=.8)
    for ax,limits in [(axes[0],(2.8,50)),(axes[1],(-.15,8.5)),(axes[2],(-.03,1.03))]:
        ax.plot(limits,limits,color='black',lw=.8,ls=':');ax.set_xlim(limits);ax.set_ylim(limits);ax.grid(alpha=.15)
    axes[0].set(xscale='log',yscale='log',xlabel='OldB covariance trace',ylabel='Age2 covariance trace',title='Total standardized variance')
    axes[0].set_xticks([3,5,10,20,40],['3','5','10','20','40'])
    axes[0].set_yticks([3,5,10,20,40],['3','5','10','20','40'])
    axes[1].set(xlabel='OldB log determinant',ylabel='Age2 log determinant',title='Gaussian uncertainty volume')
    axes[2].set(xlabel='OldB signed-mean energy fraction',ylabel='Age2 signed-mean energy fraction',title='Mean component of uncentered moment')
    axes[0].legend(frameon=False,fontsize=8)
    fig.suptitle(f'OldB versus age-matched priors: {len(rows)} contexts where both are supported',fontsize=13)
    fig.supxlabel('30 Age2-ready contexts; two oldB fallbacks excluded. Common current physical-mode coordinates; no geographic outcomes.',fontsize=9)
    for extension in ['png','pdf']:fig.savefig(ROOT/('prior_shape_comparison.'+extension),dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(11.4,7.5),layout='constrained')
    for ax,entry in zip(axes.flat,fixed):
        x=np.arange(3);available=False
        for offset,key,label,color in [(-.18,'oldB_covariance','OldB','#2878b5'),(.18,'Age2_covariance','Age2','#36a088')]:
            if entry[key] is not None:
                ax.bar(x+offset,np.diag(entry[key]),width=.35,label=label,color=color);available=True
        ax.set_title(f"{entry['case']} — H={entry['nominal_age_hours']:.2f} h, {entry['pair_count']} pairs")
        ax.set_xticks(x,['Mean motion','Inclination','RAAN']);ax.set(ylim=(0,17.5),ylabel='Admitted coefficient variance')
        status=f"OldB: {entry['oldB_status']}; Age2: {entry['Age2_status']}"
        ax.text(.02,.94,status,transform=ax.transAxes,fontsize=8,va='top',bbox=dict(facecolor='white',edgecolor='none',alpha=.85))
        if available:ax.legend(frameon=False,fontsize=8,loc='center')
        else:ax.text(.5,.5,'Neither covariance admitted; explicit fallbacks',transform=ax.transAxes,ha='center',fontsize=9)
        ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    fig.suptitle('Fixed four-case panel: admitted prior variances, without outcome selection',fontsize=13)
    for extension in ['png','pdf']:fig.savefig(ROOT/('prior_shape_fixed_cases.'+extension),dpi=180)
    plt.close(fig)


if __name__=='__main__':main()
