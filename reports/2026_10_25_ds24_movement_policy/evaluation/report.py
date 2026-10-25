"""Geographic reporting only after both scientific branches and independent audits seal."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CENTER = np.array([37.906, -122.545])
EVALUATION_SITE = np.array([37.849061591561885, -122.48574968092912])
ARMS = ('c0', 'fitted_c')
POLICIES = ('baseline', 'existing_RX1', 'movement_gate')
COLORS = dict(baseline='#333333', existing_RX1='#D55E00', movement_gate='#009E73')


def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def coordinates(x):
    return np.array([CENTER[0]+x[1]/111., CENTER[1]+x[0]/(111.32*np.cos(np.radians(CENTER[0])))])


def error_km(latlon):
    a,b=np.radians(np.array([latlon,EVALUATION_SITE]))
    h=np.sin((a[0]-b[0])/2)**2+np.cos(a[0])*np.cos(b[0])*np.sin((a[1]-b[1])/2)**2
    return float(12742*np.arcsin(np.sqrt(np.clip(h,0,1))))


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def csv_new(name, rows):
    with (HERE/name).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def guarded_inputs():
    for name in ('movement_artifacts.json','recovery_artifacts.json'):
        assert read(ROOT/'audit'/name)['status']=='passed',name
    for directory in (ROOT/'movement', ROOT/'recovery', ROOT/'recovery/repair01', ROOT/'recovery/eligibility02'):
        seal=read(directory/'scientific_seal.json')
        files=seal['files']
        if isinstance(files,dict): files=[dict(path=str(directory/name),sha256=digest) for name,digest in files.items()]
        for binding in files: assert sha(binding['path'])==binding['sha256'],binding['path']
    return read(ROOT/'cohort_ledger.json'),read(ROOT/'movement/decisions.json')['cases']


def movement_tables(ledger, decisions):
    decisions={r['case']:r for r in decisions}
    old=read(ROOT/'movement/full_data_bindings.json')
    native=read(ROOT/'audit/baseline_membership.json')['cases']
    counts={}
    with Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025/likelihood_count_audit.csv').open() as stream:
        for row in csv.DictReader(stream):
            if row['group']=='all_channels' and row['arm']=='c0':counts[row['case']]=int(row['GLRT'])
    rows=[]
    raw_changes={}
    for record in ledger['rows']:
        case=record['case']
        if not record['eligible']:
            for arm in ARMS:
                for policy in POLICIES:
                    rows.append(dict(case=case,arm=arm,policy=policy,status='input_unavailable',source=None,
                        east_km=None,north_km=None,latitude=None,longitude=None,error_km=None,curved_RMS_hz=None,
                        original_GLRT_points=None,curved_points=None,predictive_points=None,likelihood_points=None,
                        likelihood_percent_of_original_GLRT=None,selected_development_example=False))
            continue
        saved=read(old[case]['baseline_binding']['path'])['policy_arms']
        rx=read(old[case]['candidate_binding']['path'])['arms']
        for arm in ARMS:
            raw_changes[case,arm]=error_km(coordinates(rx[arm]['endpoint_east_north_km']))-error_km(coordinates(saved[arm]['endpoint_east_north_km']))
            sources=dict(baseline='baseline',existing_RX1='sharedRF50' if old[case]['original_adopted'] else 'baseline',
                movement_gate=decisions[case]['policy_source'])
            for policy,source in sources.items():
                endpoint=rx[arm] if source=='sharedRF50' else saved[arm]
                x=endpoint['endpoint_east_north_km']; ll=coordinates(x)
                np.testing.assert_allclose(ll,endpoint['endpoint_latlon'],atol=1e-12,rtol=0)
                n=native[case]['curved_points']+native[case]['predictive_points']
                rows.append(dict(case=case,arm=arm,policy=policy,status='qualified_position',source=source,
                    east_km=x[0],north_km=x[1],latitude=float(ll[0]),longitude=float(ll[1]),error_km=error_km(ll),
                    curved_RMS_hz=endpoint['RMS_hz'],original_GLRT_points=counts[case],
                    curved_points=native[case]['curved_points'],predictive_points=native[case]['predictive_points'],
                    likelihood_points=n,likelihood_percent_of_original_GLRT=100*n/counts[case],
                    selected_development_example=record['selected_development_example']))
    csv_new('positions.csv',rows)
    summary=[]
    for subset in ('all24_development','remaining22_development'):
        cases={r['case'] for r in ledger['rows'] if r['eligible'] and (subset=='all24_development' or not r['selected_development_example'])}
        for arm in ARMS:
            baseline={r['case']:r for r in rows if r['case'] in cases and r['arm']==arm and r['policy']=='baseline'}
            for policy in POLICIES:
                chosen=[r for r in rows if r['case'] in cases and r['arm']==arm and r['policy']==policy]
                errors=np.array([r['error_km'] for r in chosen]);changes=np.array([r['error_km']-baseline[r['case']]['error_km'] for r in chosen])
                summary.append(dict(subset=subset,arm=arm,policy=policy,positions=len(errors),
                    mean_km=float(np.mean(errors)),median_km=float(np.median(errors)),P95_km=float(np.quantile(errors,.95)),worst_km=float(max(errors)),
                    mean_change_km=float(np.mean(changes)),median_change_km=float(np.median(changes)),
                    improved=int(np.sum(changes < -1e-12)),worsened=int(np.sum(changes > 1e-12)),unchanged=int(np.sum(abs(changes)<=1e-12)),
                    candidate_pair_retained=sum(r['source']=='sharedRF50' for r in chosen),
                    mean_curved_RMS_hz=float(np.mean([r['curved_RMS_hz'] for r in chosen]))))
    csv_new('summary.csv',summary)
    return rows,summary,raw_changes


def recovery_tables():
    rows=[]
    for case in ('DS24-0095','DS24-0087'):
        parent=read(ROOT/'recovery'/case/'parent.json')
        policies=[('baseline',dict(policy_arms=parent['arms'],selected=None,status='baseline')),
            ('graph_policy',read(ROOT/'recovery'/case/'graph/result.json')),
            ('support_repair01_strict',read(ROOT/'recovery/repair01'/case/'result.json')),
            ('support_active_incumbent_control',read(ROOT/'recovery/eligibility02'/case/'result.json'))]
        for policy,result in policies:
            coverage=result['selected']['coverage'] if result['selected'] is not None else parent['coverage']
            for arm in ARMS:
                endpoint=result['policy_arms'][arm];x=endpoint['endpoint_east_north_km'];ll=coordinates(x)
                np.testing.assert_allclose(ll,endpoint['endpoint_latlon'],atol=1e-12,rtol=0)
                c=coverage[arm]
                rows.append(dict(case=case,arm=arm,policy=policy,status=result['status'],selected=result['selected'] is not None,
                    east_km=x[0],north_km=x[1],error_km=error_km(ll),curved_RMS_hz=endpoint['RMS_hz'],
                    original_GLRT_points=c['total_GLRT'],associated_points=c['associated'],association_percent=c['percent'],
                    curved_points=c['curved_points'],predictive_points=c['predictive_points'],likelihood_points=c['likelihood_points'],
                    active_curved_families=len(c['active_curved_families']),
                    new_active_curved_families=len(set(c['active_curved_families'])-set(parent['coverage'][arm]['active_curved_families']))))
    csv_new('recovery_positions.csv',rows)
    trial_rows=[]
    for case in ('DS24-0095','DS24-0087'):
        for branch,path in [('graph',ROOT/'recovery'/case/'graph/result.json'),
            ('support_repair01_strict',ROOT/'recovery/repair01'/case/'result.json'),
            ('support_active_incumbent',ROOT/'recovery/eligibility02'/case/'result.json')]:
            for trial in read(path)['trials']:
                versions=[('final',trial['arms'])]
                if 'ordinary_arms' in trial:versions.insert(0,('ordinary',trial['ordinary_arms']))
                for version,pair in versions:
                    for arm,endpoint in pair.items():
                        trial_rows.append(dict(case=case,branch=branch,trial_index=trial['trial_index'],version=version,arm=arm,
                            final_trial_paired_valid=trial['paired_valid'],final_trial_accepted=trial['accepted'],
                            constrained_refinement_attempted=trial.get('constrained_refinement_attempted',False),
                            error_km=error_km(coordinates(endpoint['endpoint_east_north_km'])),curved_RMS_hz=endpoint['RMS_hz'],
                            added_curved_points=trial['added_curved_points'],
                            nominees=','.join(str(row['norad']) for row in trial['additions'])))
    csv_new('recovery_trial_positions.csv',trial_rows)
    return rows


def save_figure(fig,name):
    fig.tight_layout();fig.savefig(ROOT/'figures'/name,dpi=170);plt.close(fig)


def plot_movement(rows,raw_changes,decisions):
    valid=[r for r in rows if r['status']=='qualified_position']
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        for policy in POLICIES:
            x=np.sort([r['error_km'] for r in valid if r['arm']==arm and r['policy']==policy])
            ax.step(x,np.arange(1,len(x)+1)/len(x),where='post',label=policy,color=COLORS[policy],lw=2,ls='--' if policy=='movement_gate' else '-')
        ax.set(title=arm,xlabel='Position error (km)',ylabel='Fraction of 24 usable development scans',ylim=(0,1.03));ax.grid(alpha=.2)
    axes[0].legend();fig.suptitle('Frozen complete policies; all fallback positions retained')
    save_figure(fig,'position_CDF.png')
    cases=[r['case'] for r in valid if r['arm']=='c0' and r['policy']=='baseline']
    fig,axes=plt.subplots(2,1,figsize=(13,8),sharex=True)
    for ax,arm in zip(axes,ARMS,strict=True):
        base={r['case']:r['error_km'] for r in valid if r['arm']==arm and r['policy']=='baseline'}
        for i,policy in enumerate(POLICIES[1:]):
            lookup={r['case']:r['error_km'] for r in valid if r['arm']==arm and r['policy']==policy}
            ax.bar(np.arange(len(cases))+(i-.5)*.36,[lookup[c]-base[c] for c in cases],width=.36,color=COLORS[policy],label=policy)
        ax.axhline(0,c='#555',lw=.7);ax.set(title=arm,ylabel='Change in position error (km)');ax.grid(axis='y',alpha=.2)
    axes[0].legend();axes[-1].set_xticks(range(len(cases)),[c.split('-')[-1] for c in cases],rotation=60)
    fig.suptitle('Negative bars improve geographic error; zeros include exact baseline fallback')
    save_figure(fig,'paired_position_changes.png')
    aggregates=[row for d in decisions for row in d['aggregate_gains'] if row['sigma_multiplier']==float(np.sqrt(2.))]
    gains={(r['case'],r['seed'],r['arm'],r['predictor']):r['gain'] for r in aggregates}
    decision={d['case']:d for d in decisions}
    fig,axes=plt.subplots(2,2,figsize=(12,10))
    for ai,arm in enumerate(ARMS):
        for pi,predictor in enumerate(('baseline','sharedRF50')):
            ax=axes[ai,pi]
            for case in cases:
                values=[gains[case,seed,arm,predictor] for seed in (2026102504,2026102505)]
                if any(v is None for v in values):continue
                old=decision[case]['original_policy_source']=='sharedRF50'
                ax.scatter(min(values),raw_changes[case,arm],marker='o' if old else 'x',
                    color='#009E73' if decision[case]['adopted'] else '#666666',s=35,alpha=.8)
                if case in ('DS24-0017','DS24-0095'):ax.annotate(case[-4:],(min(values),raw_changes[case,arm]),fontsize=8)
            ax.axhline(0,c='#444',lw=.7);ax.axvline(0,c='#444',lw=.7);ax.grid(alpha=.2)
            ax.set(title=f'{arm}, {predictor} predictor',xlabel='Minimum of two partition gains (primary noise scale)',ylabel='Raw full-data RX1 error − baseline error (km)')
    fig.suptitle('Held movement support and geography differ; × marks original-gate exclusions\nGreen marks new adoption; raw rejected trials are diagnostic endpoints')
    save_figure(fig,'movement_support_vs_geography.png')
    fig,axes=plt.subplots(2,2,figsize=(11,10))
    agreement=[]
    for ai,arm in enumerate(ARMS):
        for pi,predictor in enumerate(('baseline','sharedRF50')):
            ax=axes[ai,pi]
            for case in cases:
                x,y=[gains[case,seed,arm,predictor] for seed in (2026102504,2026102505)]
                if x is None or y is None:continue
                ax.scatter(x,y,color='#009E73' if decision[case]['adopted'] else '#666666',s=30)
                agreement.append(dict(case=case,arm=arm,predictor=predictor,seed2026102504_gain=x,seed2026102505_gain=y,same_sign=(x>0)==(y>0)))
            ax.axhline(0,c='#555',lw=.7);ax.axvline(0,c='#555',lw=.7);ax.grid(alpha=.2)
            ax.set(title=f'{arm}, {predictor}',xlabel='Partition 2026102504 gain',ylabel='Partition 2026102505 gain')
    fig.suptitle('Joint whole-family movement support by partition; overlapping training data')
    save_figure(fig,'partition_agreement.png');csv_new('partition_agreement.csv',agreement)
    groups=Counter()
    for d in decisions:
        categories=set()
        for reason in d['failure_reasons']:
            if 'nonpositive_or_missing_gain' in reason:categories.add('Nonpositive/missing movement sum')
            elif reason.startswith('original_'):categories.add('Original eligibility/paired policy')
            elif 'position_' in reason:categories.add('Position termination')
            elif 'train_phase' in reason:categories.add('Train phase convergence')
            elif 'fixed_phase' in reason:categories.add('Fixed phase convergence')
            elif 'gamma' in reason:categories.add('Gamma convergence')
            else:categories.add('Missing, failed or invalid job')
        groups.update(categories)
    fig,ax=plt.subplots(figsize=(10,5));labels=list(groups)
    ax.barh(labels,[groups[k] for k in labels],color='#666666');ax.set(xlabel='Scans failing requirement (categories overlap)',xlim=(0,24));ax.grid(axis='x',alpha=.2)
    fig.suptitle('Prespecified abstention reasons; no failures removed')
    save_figure(fig,'fallback_reasons.png')


def main():
    ledger,decisions=guarded_inputs()
    rows,summary,raw_changes=movement_tables(ledger,decisions)
    recovery=recovery_tables();plot_movement(rows,raw_changes,decisions)
    fig,axes=plt.subplots(1,2,figsize=(11,5))
    for ax,arm in zip(axes,ARMS,strict=True):
        for policy,offset in [('baseline',-.3),('graph_policy',-.1),('support_repair01_strict',.1),('support_active_incumbent_control',.3)]:
            selected=[r for r in recovery if r['arm']==arm and r['policy']==policy]
            ax.bar(np.arange(len(selected))+offset,[r['error_km'] for r in selected],width=.2,label=policy)
        ax.set_xticks([0,1],['0095','0087']);ax.set(title=arm,ylabel='Position error (km)');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=8);fig.suptitle('Separate baseline-only recovery pilot and support control')
    save_figure(fig,'recovery_position_errors.png')
    output=dict(status='complete',evaluation_only_GPS=EVALUATION_SITE.tolist(),no_new_fits_or_policy_selection=True,
        source_sha256=sha(Path(__file__)),movement_summary=summary,recovery_positions=recovery,
        population=34,eligible=24,unavailable=10,position_rows=len(rows),
        geographic_reporting_after_scientific_seals={name:sha(ROOT/name/'scientific_seal.json') for name in ('movement','recovery','recovery/repair01','recovery/eligibility02')},
        audit_bindings={name:sha(ROOT/'audit'/name) for name in ('movement_artifacts.json','recovery_artifacts.json')},
        limitation='Previously examined same-site development replication; family crossfit scores do not directly hold out the saved full-data displacement')
    write_new(HERE/'summary.json',output)
    write_new(HERE/'seal.json',dict(files={str(p.relative_to(ROOT)):sha(p) for directory in (HERE,ROOT/'figures') for p in sorted(directory.rglob('*')) if p.is_file() and p.name!='seal.json'}))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
