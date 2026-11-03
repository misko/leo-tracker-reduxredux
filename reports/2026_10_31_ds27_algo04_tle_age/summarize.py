"""Family-level correlation summaries and static scientific figures."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr, rankdata
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
METRICS={
 'phase_s':'Signed fitted phase (s)',
 'phase_innovation_s':'Signed phase departure from prior mean (s)',
 'abs_phase_s':'Absolute fitted phase (s)',
 'phase_prior_sigma_s':'Phase prior width (s)',
 'abs_phase_innovation_s':'Absolute phase departure from prior mean (s)',
 'abs_phase_pull':'Absolute phase departure / prior width',
 'orbital_pull_norm':'Orbital correction norm (prior units)',
 'abs_mean_motion_rev_day':'Absolute mean-motion correction (rev/day)',
 'abs_inclination_deg':'Absolute inclination correction (deg)',
 'abs_raan_deg':'Absolute RAAN correction (deg)',
 'radial_prior_km':'Radial prior width (km)',
 'orbit_frequency_rms_hz':'Orbital CFO correction RMS (Hz)',
 'mean_abs_track_bias_hz':'Mean absolute track offset (Hz)',
 'rms_hz':'Calibration residual RMS (Hz)',
}


def rho(x,y):
    if len(x)<4 or np.ptp(x)<1e-12 or np.ptp(y)<1e-12:
        return float('nan')
    return float(spearmanr(x,y).statistic)


def partial_rank(d, metric, groups):
    """Pearson correlation of ranks after projecting out specified fixed effects."""
    x,y=rankdata(d.tle_age_h),rankdata(d[metric])
    design=[np.ones((len(d),1))]
    for key in groups:
        design.append(pd.get_dummies(d[key],drop_first=True,dtype=float).to_numpy())
    a=np.column_stack(design)
    # A saturated scan/satellite design can leave one residual direction and
    # mechanically return +/-1. Do not call that an estimable relationship.
    if len(d)-np.linalg.matrix_rank(a)<5:
        return float('nan')
    r=np.column_stack([x,y]);r-=a@np.linalg.lstsq(a,r,rcond=None)[0]
    if np.linalg.norm(r[:,0])<1e-8 or np.linalg.norm(r[:,1])<1e-8:
        return float('nan')
    return float(np.corrcoef(r.T)[0,1])


def correlation(d,metric,seed=431):
    if metric in ('rms_hz','mean_abs_track_bias_hz'):
        d=d[d.role=='calibration']  # Predictive-profile and calibration RMS differ.
    d=d.dropna(subset=['tle_age_h',metric]).copy()
    x,y=d.tle_age_h.to_numpy(),d[metric].to_numpy()
    groups=[np.flatnonzero(d.case.to_numpy()==v) for v in d.case.unique()]
    rng=np.random.default_rng(seed)
    boots=[]
    for _ in range(1500):
        ix=np.concatenate([groups[k] for k in rng.integers(len(groups),size=len(groups))])
        boots.append(rho(x[ix],y[ix]))
    ci=np.nanpercentile(boots,[2.5,97.5])
    loo=[rho(d[d.case!=s].tle_age_h,d[d.case!=s][metric]) for s in d.case.unique()]
    sat=d.groupby('norad')[['tle_age_h',metric]].median()
    return dict(metric=metric,n=len(d),scans=d.case.nunique(),satellites=d.norad.nunique(),
                rho=rho(x,y),scan_bootstrap_lo=ci[0],scan_bootstrap_hi=ci[1],
                within_scan=partial_rank(d,metric,['case']),
                scan_satellite_adjusted=partial_rank(d,metric,['case','norad']),
                satellite_median=rho(sat.tle_age_h,sat[metric]),
                leave_one_scan_min=min(loo),leave_one_scan_max=max(loo))


def load():
    rows=[];receivers=[];checks=[];inventory=[]
    for f in sorted((ROOT/'cases').glob('DS27-*.json')):
        z=json.loads(f.read_text())
        if z['state']!='complete':
            raise ValueError(f'Replay failed: {f}')
        rows+=z['families'];receivers+=z['receivers'];checks+=z['checks'];inventory+=z['family_inventory']
    d=pd.DataFrame(rows);r=pd.DataFrame(receivers);c=pd.DataFrame(checks);i=pd.DataFrame(inventory)
    assert not d.duplicated(['case','arm','norad']).any()
    assert set(map(tuple,d[d.arm=='c0'][['case','norad']].values))==set(map(tuple,d[d.arm=='fitted_c'][['case','norad']].values))
    for name,frame in [('families',d),('receiver_calibration',r),('replay_checks',c),('associated_family_inventory',i)]:
        frame.to_csv(ROOT/(name+'.csv'),index=False)
    return d,r,c,i


def plot_scatter(d,stats):
    keys=['abs_phase_s','phase_prior_sigma_s','abs_phase_pull','orbital_pull_norm','abs_mean_motion_rev_day','rms_hz']
    cases=sorted(d.case.unique());colors={c:plt.cm.tab20(k) for k,c in enumerate(cases)}
    fig,axs=plt.subplots(2,3,figsize=(15,9),layout='constrained')
    for ax,key in zip(axs.flat,keys):
        z=d[d.role=='calibration'] if key=='rms_hz' else d
        a=z[z.arm=='c0'].dropna(subset=[key]); b=z[z.arm=='fitted_c'].dropna(subset=[key])
        ax.scatter(a.tle_age_h,a[key],s=20,facecolors='none',edgecolors='0.7',alpha=.55,label='c = 0')
        for case,v in b.groupby('case'):
            ax.scatter(v.tle_age_h,v[key],s=25,color=colors[case],alpha=.8,label=case)
        for frame,style in [(a,'--'),(b,'-')]:
            bins=pd.cut(frame.tle_age_h,[0,6,12,18,24,36,48,72])
            med=frame.groupby(bins,observed=True)[['tle_age_h',key]].median()
            ax.plot(med.tle_age_h,med[key],style,color='black',lw=1.4)
        sr=stats[(stats.arm=='fitted_c')&(stats.metric==key)].iloc[0]
        ax.set_title(f"ρ = {sr.rho:+.2f}; scan-bootstrap 95% CI [{sr.scan_bootstrap_lo:+.2f}, {sr.scan_bootstrap_hi:+.2f}]",fontsize=10)
        ax.set(xlabel='TLE epoch age at scan start (hours)',ylabel=METRICS[key]);ax.grid(alpha=.18)
        if key=='abs_mean_motion_rev_day':ax.set_yscale('log')
    fig.suptitle('DS27 / ALGO04: older TLEs versus fitted satellite corrections\nColored dots: fitted c; hollow dots: c = 0; black lines: age-bin medians',fontsize=15)
    handles,labels=axs.flat[0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=7,fontsize=8)
    fig.savefig(ROOT/'age_vs_nuisance.png',dpi=170);plt.close(fig)


def plot_robustness(stats):
    keys=['abs_phase_s','abs_phase_innovation_s','phase_prior_sigma_s','abs_phase_pull','orbital_pull_norm','abs_mean_motion_rev_day','abs_inclination_deg','abs_raan_deg','orbit_frequency_rms_hz','mean_abs_track_bias_hz','rms_hz']
    columns=['rho','within_scan','scan_satellite_adjusted','satellite_median']
    fig,axs=plt.subplots(1,2,figsize=(14,8),layout='constrained')
    for ax,arm in zip(axs,['c0','fitted_c']):
        v=stats[stats.arm==arm].set_index('metric').loc[keys,columns].values
        im=ax.imshow(v,vmin=-1,vmax=1,cmap='RdBu_r',aspect='auto')
        ax.set_yticks(range(len(keys)),[METRICS[k] for k in keys] if arm=='c0' else ['']*len(keys),fontsize=9)
        ax.set_xticks(range(4),['Pooled','Within\nscan','Scan +\nsatellite','Median per\nsatellite'],fontsize=9)
        ax.set_title('c = 0' if arm=='c0' else 'Fitted c')
        for (j,k),value in np.ndenumerate(v):
            ax.text(k,j,f'{value:+.2f}' if np.isfinite(value) else 'Insufficient\nrepeat data',ha='center',va='center',fontsize=8,color='white' if abs(value)>.65 else 'black')
    fig.colorbar(im,ax=axs,shrink=.6,label='Rank correlation / adjusted rank correlation')
    fig.suptitle('Does the apparent relationship survive scan and satellite controls?',fontsize=15)
    fig.savefig(ROOT/'correlation_controls.png',dpi=170);plt.close(fig)


def plot_radio(r):
    keys=['rx1_low_drift_hz_s','rx1_high_drift_hz_s','rx2_low_drift_hz_s','rx2_high_drift_hz_s','smooth_rms_hz','c_hz_ghz']
    fig,axs=plt.subplots(2,3,figsize=(14,8),layout='constrained');stats=[]
    for ax,key in zip(axs.flat,keys):
        for arm,marker,color in [('c0','o','#929292'),('fitted_c','x','#6b2690')]:
            z=r[r.arm==arm];y=abs(z[key]);v=rho(z.median_tle_age_h,y)
            ax.scatter(z.median_tle_age_h,y,marker=marker,color=color,label=f'{arm}: ρ={v:+.2f}')
            stats.append(dict(arm=arm,metric=key,rho=v,n=len(z)))
            if arm=='fitted_c':
                for _,p in z.iterrows():ax.annotate(p.case[-4:],(p.median_tle_age_h,abs(p[key])),fontsize=7,xytext=(3,2),textcoords='offset points')
        ax.set(xlabel='Median family TLE age in scan (hours)',ylabel='Absolute '+key.replace('_',' '));ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('Receiver nuisance terms: 13 scan-level observations, not hundreds of independent satellites',fontsize=14)
    fig.savefig(ROOT/'receiver_terms.png',dpi=170);plt.close(fig)
    for key in ['rx1_band_offset_hz','rx2_band_offset_hz','low_rx_offset_hz','high_rx_offset_hz']:
        for arm in ['c0','fitted_c']:
            z=r[r.arm==arm]
            stats.append(dict(arm=arm,metric=key,rho=rho(z.median_tle_age_h,abs(z[key])),n=len(z)))
    return stats


def main():
    d,r,c,inv=load()
    stats=pd.DataFrame([dict(arm=arm,**correlation(d[d.arm==arm],key)) for arm in ('c0','fitted_c') for key in METRICS])
    stats.to_csv(ROOT/'correlations.csv',index=False)
    plot_scatter(d,stats);plot_robustness(stats)
    radio=plot_radio(r);pd.DataFrame(radio).to_csv(ROOT/'receiver_correlations.csv',index=False)
    byscan=d.groupby(['case','arm']).agg(families=('norad','size'),age_median_h=('tle_age_h','median'),age_min_h=('tle_age_h','min'),age_max_h=('tle_age_h','max'),phase_abs_median_s=('abs_phase_s','median'),phase_pull_median=('abs_phase_pull','median'),orbital_norm_median=('orbital_pull_norm','median')).reset_index()
    byscan.to_csv(ROOT/'per_scan.csv',index=False)
    bins=d[d.arm=='fitted_c'].copy();bins['age_bin_h']=pd.cut(bins.tle_age_h,[0,12,24,36,48])
    b=bins.groupby('age_bin_h',observed=True).agg(families=('norad','size'),phase_median_s=('abs_phase_s','median'),prior_width_median_s=('phase_prior_sigma_s','median'),phase_pull_median=('abs_phase_pull','median'),orbital_norm_median=('orbital_pull_norm','median'))
    b['calibration_rms_median_hz']=bins[bins.role=='calibration'].groupby('age_bin_h',observed=True).rms_hz.median()
    b.to_csv(ROOT/'age_bins.csv')
    bins.nlargest(10,'abs_phase_pull').to_csv(ROOT/'largest_phase_departures.csv',index=False)
    summary=dict(scans=int(d.case.nunique()),family_scan_pairs=int(len(d)//2),unique_satellites=int(d.norad.nunique()),
                 unique_tle_versions=int(d[['norad','epoch_utc_ns']].drop_duplicates().shape[0]),
                 repeated_satellites=int((d[d.arm=='c0'].groupby('norad').size()>1).sum()),
                 age_min_h=float(d.tle_age_h.min()),age_max_h=float(d.tle_age_h.max()),
                 role_counts=d[d.arm=='c0'].role.value_counts().to_dict(),
                 owned_family_counts=inv[inv.arm=='c0'].role.value_counts().to_dict(),
                 max_replay_objective_difference=float(c.objective_difference.abs().max()),
                 max_replay_state_difference=float(c.state_max_difference.abs().max()))
    (ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2));print(stats[['arm','metric','n','rho','scan_bootstrap_lo','scan_bootstrap_hi','within_scan','scan_satellite_adjusted']].to_string(index=False))


if __name__=='__main__':main()
