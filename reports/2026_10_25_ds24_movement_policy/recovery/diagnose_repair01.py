"""RF-only views using immutable graph results and repaired support records."""

import numpy as np
import matplotlib.pyplot as plt

import recovery as r
import repair01 as repair
import eligibility02 as eligibility
import diagnostics as diag


def main():
    repair.verify()
    seal=r.read(eligibility.OUT/'scientific_seal.json')
    for name,digest in seal['files'].items():
        if r.sha(eligibility.OUT/name)!=digest:raise ValueError('eligibility-corrected RF result changed')
    r.build=repair.corrected_build
    output=r.HERE/'diagnostics_repair01';output.mkdir(exist_ok=False)
    records=[]
    for case in r.CASES:
        d=r.context(case);parent=r.read(r.HERE/case/'parent.json')
        policies=[('baseline','graph',None,parent['arms'],parent['coverage'])]
        graph=r.read(r.HERE/case/'graph/result.json')
        control=r.read(eligibility.OUT/case/'result.json')
        for label,kind,result in [('graph_policy','graph',graph),('support_active_incumbent_control','support',control)]:
            selected=result['selected']
            policies.append((label,kind,selected,result['policy_arms'],selected['coverage'] if selected else parent['coverage']))
        destination=output/case;destination.mkdir()
        for label,kind,selected,arms,coverage in policies:
            dd=d if selected is None else dict(d,node=selected['node'],keep=np.asarray(selected['mask'],bool),
                means=np.asarray(selected['means']),entries=selected['entries'])
            for arm in r.ARMS:
                info,p,c=diag.information(dd,arms[arm],arm,kind if selected is not None else 'graph')
                r.write_new(destination/(label+'_'+arm+'_information.json'),info)
                records.append(dict(case=case,policy=label,arm=arm,**{k:info[k] for k in ('major_local_sigma_km','minor_local_sigma_km')}))
                if arm=='fitted_c':
                    diag.views(dd,arms[arm],coverage[arm],p,c,destination,label)
                    family=sorted(info['family_influence'],key=lambda row:-row['weak_direction_information_gain'])[:10]
                    fig,ax=plt.subplots(figsize=(9,5))
                    ax.barh(range(len(family)),[row['weak_direction_information_gain'] for row in family])
                    ax.set_yticks(range(len(family)),[str(row['norad']) for row in family]);ax.invert_yaxis()
                    ax.set(xlabel='Weak-direction information lost when family removed (km⁻²)',ylabel='Model family',
                        title=case+' '+label+' conditional curved-family information')
                    ax.grid(axis='x',alpha=.2);fig.tight_layout()
                    fig.savefig(destination/(label+'_family_information.png'),dpi=150);plt.close(fig)
    r.write_new(output/'summary.json',dict(rows=records,no_GPS=True,no_position_refits=True,
        original_scientific_seal_sha256=r.sha(r.HERE/'scientific_seal.json'),
        repair_scientific_seal_sha256=r.sha(repair.OUT/'scientific_seal.json'),
        eligibility_scientific_seal_sha256=r.sha(eligibility.OUT/'scientific_seal.json'),
        strict_original_layout_control_is_baseline_and_preserved=True,
        diagnostic_source_sha256={str(path):r.sha(path) for path in [r.HERE/'diagnostics.py',r.HERE/'diagnose_repair01.py',r.HERE/'repair01.py',r.HERE/'eligibility02.py']}))
    fig,axes=plt.subplots(1,2,figsize=(12,5))
    for ax,case in zip(axes,r.CASES,strict=True):
        rows=[v for v in records if v['case']==case and v['arm']=='fitted_c']
        ax.bar(range(len(rows)),[v['major_local_sigma_km'] for v in rows])
        ax.set_xticks(range(len(rows)),[v['policy'] for v in rows],rotation=15)
        ax.set(title=case,ylabel='Conditional curved weak-axis scale (km)');ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(output/'weak_direction_information.png',dpi=150);plt.close(fig)
    r.write_new(output/'seal.json',dict(files={str(p.relative_to(output)):r.sha(p) for p in sorted(output.rglob('*')) if p.is_file()}))


if __name__=='__main__':main()
