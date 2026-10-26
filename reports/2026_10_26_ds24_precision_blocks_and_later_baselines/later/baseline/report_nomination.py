"""Saved-only RF readiness table/figure and compact baseline publication list."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

BASE=Path(__file__).resolve().parent;NOM=BASE/'nomination';WORK=BASE/'work'
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def verify(path):
    for p,h in read(path)['files'].items():
        if sha(p)!=h:raise ValueError('sealed saved source changed: '+p)


def report():
    verify(BASE/'later_RF_seal.json');verify(NOM/'RF_seal.json')
    out=BASE/'rf_readiness';out.mkdir(exist_ok=False);rows=[];cases=[]
    for result in read(NOM/'summary.json')['rows']:
        case=result['case'];path=WORK/'family_cavity/position'/(case+'.json');parent=read(path)
        selected=parent['selected'] if parent['accepted'] else None
        node=selected['node'] if selected else parent['baseline_node']
        selection=read(NOM/case/'selection.json');coverage=read(NOM/case/'ownership.json')['coverage']
        choices=[]
        for role in ('target','control'):
            owner=selection[role]
            if owner is None:continue
            index=next(i for i,r in enumerate(node['seed']['rows']) if r['component']==owner['owner'])
            row=node['seed']['rows'][index]
            choice=dict(role=role,owner=owner['owner'],family=owner['family'],receiver=owner['receiver'],channel=owner['channel'],
                rf_hz=owner['rf_hz'],points=owner['points'],quality_status=owner['quality_status'],
                candidate_index=row['candidate_index'],graph_alias=node['aliases'][index],
                original_native_IDs=owner['observation_ids'],score_km_per_Hz_RMS=owner['arms'])
            choices.append(choice)
            rows.append(dict(case=case,role=role,owner=owner['owner'],family=owner['family'],points=owner['points'],
                quality_status=owner['quality_status'],candidate_index=row['candidate_index'],graph_alias=node['aliases'][index],
                c0_m_per_Hz_RMS=1000*owner['arms']['c0'],fitted_c_m_per_Hz_RMS=1000*owner['arms']['fitted_c']))
        summary=dict(case=case,baseline_status='complete',source_parent_path=str(path),source_parent_sha256=sha(path),
            reconstructed_fresh_reference=parent['reconstructed_fresh_reference'],cavity_adopted=parent['accepted'],
            selected_complete_owners=choices,phase_diagnostic=result['absolute_phase_diagnostic'],arms={})
        for arm in ('c0','fitted_c'):
            a=parent['policy_arms'][arm];cov=coverage[arm]
            summary['arms'][arm]=dict(endpoint_east_north_km=a['endpoint_east_north_km'],phase_reference=a['phase_reference'],
                full_VI_objective=a['negative_twice_elbo'],conditional_RMS_hz=a['RMS_hz'],
                producer_active_gates_pass=all(g['compatible'] for g in a['gates']['tracks']),
                final_phase_change_s=a['final_phase_change_s'],curved_IDs=cov['curved_points'],predictive_IDs=cov['predictive_points'],
                fixed_likelihood_IDs=cov['likelihood_points'],total_GLRT=cov['total_GLRT'],associated_IDs=cov['associated'],
                associated_percent=cov['percent'],postfit_only_IDs=len(cov['postfit_only_observation_ids']))
        cases.append(summary);write(out/(case+'.json'),summary)
    with (out/'owner_scores.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(out/'summary.json',dict(cases=cases,selected_native_receiver_windows=402,deduplicated_physical_probes=402,
        original_nomination_rule=True,no_IQ_detector_correction_position_fit_or_GPS=True,
        nomination_RF_seal_sha256=sha(NOM/'RF_seal.json'),baseline_RF_seal_sha256=sha(BASE/'later_RF_seal.json')))
    fig,axes=plt.subplots(1,4,figsize=(13,4.8),sharey=True,layout='constrained')
    for ax,q in zip(axes,cases):
        group=[r for r in rows if r['case']==q['case']]
        for index,role in enumerate(('target','control')):
            row=next(r for r in group if r['role']==role)
            ax.scatter(index-.08,row['c0_m_per_Hz_RMS'],color='#176b8b',marker='o',label='c=0' if index==0 else None)
            ax.scatter(index+.08,row['fitted_c_m_per_Hz_RMS'],color='#b06624',marker='s',label='Fitted c' if index==0 else None)
            ax.annotate(f"{row['family']}\n{row['points']} IDs",(index,max(row['c0_m_per_Hz_RMS'],row['fitted_c_m_per_Hz_RMS'])),
                xytext=(0,8),textcoords='offset points',ha='center',fontsize=9)
        ax.set_title(q['case']);ax.set_xticks([0,1],['Target','Control']);ax.set_xlim(-.45,1.45);ax.grid(axis='y',alpha=.25)
        ax.set_yscale('log');ax.set_ylim(.08,40)
    axes[0].set_ylabel('Local weak-axis susceptibility (m per 1 Hz RMS)');axes[0].legend(loc='upper right',fontsize=9)
    fig.suptitle('Original RF-only complete-owner selection\nConditional sensitivity, not a measured bias or position-gain forecast',fontsize=12)
    fig.savefig(out/'selected_owner_susceptibility.png',dpi=170);plt.close(fig)
    write(out/'seal.json',dict(files={str(p):sha(p) for p in list(out.iterdir())+[Path(__file__),NOM/'RF_seal.json',BASE/'later_RF_seal.json'] if p.is_file()}))


def manifest():
    if (BASE/'lean_publication.json').exists():raise FileExistsError('publication list already final')
    files=[p for p in BASE.iterdir() if p.is_file() and p.suffix in ('.py','.md','.json') and p.name!='lean_publication.json']
    files +=[p for p in NOM.iterdir() if p.is_file() and p.suffix in ('.py','.md','.json')]
    files +=[p for p in (BASE/'rf_readiness').iterdir() if p.is_file()]
    for case in ('LATER4-0001','LATER4-0002','LATER4-0003','LATER4-0004'):
        files +=[NOM/case/n for n in ('selection.json','checks.json','result.json')]
    published=[dict(path=str(p.relative_to(BASE)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(set(files))]
    included={str(p) for p in files};external={}
    for seal in (BASE/'later_RF_seal.json',NOM/'RF_seal.json'):
        external.update({p:h for p,h in read(seal)['files'].items() if p not in included})
    protocol=read(BASE/'later_protocol.json')
    external.update({p:h for k in ('source_bindings','input_bindings') for p,h in protocol[k].items() if p not in included})
    write(BASE/'lean_publication.json',dict(schema='lean-scientific-publication/v1',root=str(BASE),published=published,
        published_files=len(published),published_bytes=sum(x['bytes'] for x in published),
        external_inputs=[dict(path=p,sha256=h) for p,h in sorted(external.items())],
        all402_selected_native_ID_probe_mappings='nomination/complete_requests.json',
        raw_parent_ownership_and_banks_external_hash_bound=True,full_replay_requires_external_inputs=True))
    print(json.dumps(dict(files=len(published),bytes=sum(x['bytes'] for x in published),external=len(external))))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=('report','manifest'));a=p.parse_args()
    {'report':report,'manifest':manifest}[a.action]()
