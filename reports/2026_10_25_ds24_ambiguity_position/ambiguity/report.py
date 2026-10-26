"""Saved fixed-position profiles, conservative secants and source qualification."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent;OUT=HERE/'report'
CASES=('DS24-0011','DS24-0012');ARMS=('c0','fitted_c');PROBES=('minus','center','plus');WEIGHTS=(.25,.5,.75)
read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def table(name,rows):
    if not rows:return
    with (OUT/name).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    seal=read(HERE/'RF_seal.json')
    for path,h in seal['files'].items():
        if sha(path)!=h:raise ValueError('scientific file changed: '+path)
    OUT.mkdir(exist_ok=False)
    execution=read(HERE/'execution.json');secants=[];profiles=[];components=[];weights=[];triage=[];sources=[]
    inventory=read(Path('/srv/bulk/leo/research/ds24-next-directions-review-r01/identity/inventory.json'))
    for case in CASES:
        target=next(row['target'] for row in inventory['rows'] if row['case']==case)
        sources.append(dict(case=case,component=target['component'],points=target['points'],
            original_nomination_compatible=target['original_nomination_compatible'],
            original_full_parent_mask_rejects_whole_source=target['parent_final_mask_rejected_whole_source'],
            complete_source_active_curvature_flag=target['active_curvature_persisted'],RX_channel_owners=target['offered_new_family_RX_channel_owners'],
            independently_qualified_association=target['qualified_association'],operational_adoption=False))
        end=read(HERE/case/'execution.json') if (HERE/case/'execution.json').exists() else {}
        for row in end.get('contrasts',[]):
            interval=row.get('proxy_interval_km')
            secants.append(dict(case=case,arm=row['arm'],physical_class_weight=row['weight'],
                delta_secant_objective_per_km=row['delta_finite_difference_per_km'],point_proxy_m=1000*row['archived_c0_curvature_scaled_secant_proxy_km'],
                bounds_available=row['bounds_available'],proxy_lower_m=1000*interval[0] if interval else None,proxy_upper_m=1000*interval[1] if interval else None,
                interval_supports_abs25m=row.get('interval_supports_material_25m',False),
                point_quadratures_stable=row['all_point_quadratures_stable'],true_derivative=False,achieved_movement=False))
        for prior in WEIGHTS:
            group=[row for row in secants if row['case']==case and row['physical_class_weight']==prior]
            triage.append(dict(case=case,physical_class_weight=prior,
                interval_material_in_both_arms=len(group)==2 and all(row['interval_supports_abs25m'] for row in group),
                point_abs25m_in_both_arms=len(group)==2 and all(abs(row['point_proxy_m'])>=25 for row in group),
                point_estimate_is_qualified_policy=False))
        for probe in PROBES:
            for arm in ARMS:
                path=HERE/case/probe/(arm+'_summary.json')
                if not path.exists():continue
                row=read(path);parent=read(HERE/case/probe/(arm+'_parent.json'))
                objects=[('hard',row['hard']),('unknown',row['unknown']),('best_physical_point_envelope',dict(objective=row['best_physical_point_objective']))]
                objects += [('mixture_'+str(prior),row['mixture'][str(prior)]) for prior in WEIGHTS]
                for label,obj in objects:
                    profiles.append(dict(case=case,arm=arm,probe=probe,offset_km={'minus':-.1,'center':0,'plus':.1}[probe],model=label,
                        conditional_target_objective=obj.get('objective'),lower_objective=obj.get('lower_objective'),upper_objective=obj.get('upper_objective'),
                        parent_negative_twice_ELBO=parent['parent_negative_twice_ELBO'],
                        surrogate_joint_parent_plus_target=parent['parent_negative_twice_ELBO']+obj['objective'] if obj.get('objective') is not None else None,
                        parent_original_RF_gates_pass=parent['original_remaining_gates_pass'],operational_adoption=False))
                if probe=='center':
                    labels=[model['norad'] for model in row['models']]+['unknown']
                    for prior in WEIGHTS:
                        for label,value in zip(labels,row['mixture'][str(prior)].get('conditional_model_weights',[])):
                            weights.append(dict(case=case,arm=arm,physical_class_prior=prior,hypothesis=label,conditional_density_weight=value,calibrated_identity_probability=False))
    for slot in execution['all108_slots']:
        path=HERE/slot['case']/slot['probe']/(slot['arm']+'_'+str(slot['identity'])+'.json')
        row=read(path) if path.exists() else {}
        components.append(dict(**slot,objective=row.get('objective'),full_lower_logZ=row.get('full_support_lower_log_integral',row.get('lower_logZ')),
            full_upper_logZ=row.get('full_support_upper_log_integral',row.get('upper_logZ')),
            primary_point_GL_stable=row.get('point_quadrature_stable'),absolute_objective_precision_qualified=row.get('numerically_qualified',False),
            independent_null_reference_passed=row.get('reference_passed'),certified_empty_support=row.get('empty_support_certified',False)))
    table('source_status.csv',sources);table('profiles.csv',profiles);table('secants.csv',secants);table('component_contexts.csv',components);table('center_model_weights.csv',weights)
    body=dict(execution=execution,triage=triage,sources=sources,secants=secants,
        completed_component_slots=sum(row['status']=='complete' for row in components),declared_component_slots=108,
        absolute_objective_precision_qualified=sum(row['absolute_objective_precision_qualified'] for row in components if row['identity']!='unknown'),
        points_are_potential_added_factor_effects=True,current_reference_changed=False,new_inference=False)
    with (OUT/'summary.json').open('x') as stream:json.dump(body,stream,indent=2);stream.write('\n')
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for i,case in enumerate(CASES):
        for j,arm in enumerate(ARMS):
            ax=axes[i,j]
            for model,label,color in [('hard','Fixed hard nominee','#333333'),('best_physical_point_envelope','Best-of8 point envelope','#d48724'),('mixture_0.5','Mixture: physical mass0.5','#00796b'),('unknown','Fixed proper unknown','#65758b')]:
                rows=[row for row in profiles if row['case']==case and row['arm']==arm and row['model']==model]
                center=next((row['conditional_target_objective'] for row in rows if row['probe']=='center'),None)
                if center is None:continue
                ax.plot([row['offset_km'] for row in rows],[row['conditional_target_objective']-center for row in rows],'o-',label=label,color=color,ms=4)
            ax.axhline(0,lw=.6,color='gray');ax.set_xticks([-.1,0,.1]);ax.grid(alpha=.2)
            ax.set_title(case+' · '+('c=0' if arm=='c0' else 'fitted c'));ax.set_xlabel('Offset along frozen c0 RF weak axis (km)')
            ax.set_ylabel('Conditional target objective − own center');ax.legend(fontsize=7)
    fig.suptitle('Three fixed RF probes: point-estimate profiles, not position fits\nParent factor is shared; displayed target scores do not establish accepted identity.',fontsize=11)
    fig.savefig(OUT/'fixed_RF_profiles.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,5),layout='constrained')
    for ax,case in zip(axes,CASES):
        ax.axhspan(-25,25,color='gray',alpha=.12,label='±25m research screen')
        for arm,color,shift in [('c0','#00796b',-.012),('fitted_c','#b34c32',.012)]:
            rows=[row for row in secants if row['case']==case and row['arm']==arm]
            for index,row in enumerate(rows):
                x=row['physical_class_weight']+shift;y=row['point_proxy_m']
                if row['bounds_available']:
                    ax.vlines(x,row['proxy_lower_m'],row['proxy_upper_m'],color=color,lw=2)
                    ax.plot([x,x],[row['proxy_lower_m'],row['proxy_upper_m']],'_',color=color)
                ax.plot(x,y,'o',color=color,label=arm if index==0 else None)
        ax.set_yscale('symlog',linthresh=25);ax.axhline(0,color='black',lw=.6)
        ax.set_xticks(WEIGHTS);ax.set_xlabel('Predeclared total physical-class prior mass');ax.grid(axis='y',alpha=.2)
        ax.set_title(case);ax.set_ylabel('Archived-c0-curvature-scaled secant proxy (m)');ax.legend(fontsize=8)
    fig.suptitle('Mixture minus fixed hard nominee\nDots: point proxies. Lines: conservative full-evidence intervals. Neither is achieved displacement.',fontsize=11)
    fig.savefig(OUT/'secant_proxy_bounds.png',dpi=180);plt.close(fig)
    files={str(path):sha(path) for path in OUT.iterdir() if path.is_file()};files[str(Path(__file__))]=sha(__file__)
    with (OUT/'seal.json').open('x') as stream:json.dump(dict(files=files,RF_seal_sha256=sha(HERE/'RF_seal.json')),stream,indent=2);stream.write('\n')
    print(json.dumps(dict(completed_slots=body['completed_component_slots'],secants=len(secants),triage=triage)))


if __name__=='__main__':main()
