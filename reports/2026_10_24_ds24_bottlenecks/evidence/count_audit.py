"""Audit legacy and current likelihood membership schemas against exact IDs."""
import csv
from audit_evidence import OUT,ROOTS,HALF,ARMS,read,write

def main():
    cases=read(HALF/'summary.json')['baseline']['c0']['common_cases']
    rows=[]
    for case in cases:
        for group,root in ROOTS.items():
            d=read(root/'family_cavity/position'/(case+'.json'))
            all_ids={o['observation_id'] for o in read(root/case/'observations.json')}
            for arm in ARMS:
                saved=d['policy_arms'][arm]
                curved=[oid for r in saved['gates']['tracks'] if r['compatible'] for oid in r['observation_ids']]
                predictive=[oid for r in saved.get('linear_gates',[]) if r['compatible'] for oid in r['observation_ids']]
                assert len(curved)==len(set(curved))==saved['active_points']
                assert len(predictive)==len(set(predictive))
                assert not (set(curved)&set(predictive))
                assert set(curved)|set(predictive)<=all_ids
                assert all(r['compatible'] for r in saved['gates']['tracks'])
                assert all(r['compatible'] for r in saved.get('linear_gates',[]))
                schema_count=saved.get('predictive_points',saved.get('additional_predictive_points',0))
                assert len(predictive)==schema_count
                published=saved['active_points']+saved.get('predictive_points',0)
                rows.append(dict(case=case,group=group,arm=arm,GLRT=len(all_ids),curved_unique_ids=len(curved),predictive_unique_ids=len(predictive),likelihood_union_ids=len(set(curved)|set(predictive)),published_count=published,omitted_predictive_ids=len(curved)+len(predictive)-published,predictive_count_field='predictive_points' if 'predictive_points' in saved else 'additional_predictive_points',curved_predictive_disjoint=True,all_ids_original=True,all_gates_compatible=True))
    with (OUT/'likelihood_count_audit.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    totals={}
    for group in ROOTS:
        for arm in ARMS:
            rr=[r for r in rows if r['group']==group and r['arm']==arm]
            total={k:sum(r[k] for r in rr) for k in ('GLRT','curved_unique_ids','predictive_unique_ids','likelihood_union_ids','published_count','omitted_predictive_ids')}
            total['corrected_percent']=100*total['likelihood_union_ids']/total['GLRT']
            total['omitted_cases']=[dict(case=r['case'],omitted=r['omitted_predictive_ids']) for r in rr if r['omitted_predictive_ids']]
            totals[group+'/'+arm]=total
    write(OUT/'likelihood_count_audit.json',dict(all_assertions_passed=True,rows=rows,totals=totals))
    print(totals)

if __name__=='__main__':main()
