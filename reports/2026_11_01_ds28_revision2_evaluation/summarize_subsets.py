"""Reporting-only separation of retained and newly acquired DS28 scans."""
import csv,json
from common import *

def main():
    assert (ROOT/'inference-seal.json').exists()
    rows=list(csv.DictReader((ROOT/'position-errors.csv').open()))
    old={r['dataset_label'] for r in read(ROOT/'dataset/previous-revision-manifest.json')['members']}
    all_cases={r['dataset_label'] for r in read(ROOT/'dataset/manifest.json')['members']}
    results=[]
    for subset,cases in [('all',all_cases),('original_revision_1',old),('new_in_revision_2',all_cases-old)]:
        for arm in ARMS:
            for method in ('ALGO05',*POLICIES):
                rr=[r for r in rows if r['case'] in cases and r['arm']==arm and r['method']==method]
                errors=np.array([float(r['error_m']) for r in rr])
                baseline={r['case']:float(r['error_m']) for r in rows if r['case'] in cases and r['arm']==arm and r['method']=='ALGO05'}
                delta=np.array([float(r['error_m'])-baseline[r['case']] for r in rr])
                total=sum(int(r['total']) for r in rr);associated=sum(int(r['associated']) for r in rr)
                results.append(dict(subset=subset,arm=arm,method=method,members=len(cases),usable=len(rr),
                    mean_m=float(errors.mean()),median_m=float(np.median(errors)),p90_m=float(np.quantile(errors,.9)),
                    worst_m=float(errors.max()),within_500m=int((errors<=500).sum()),over_1km=int((errors>1000).sum()),
                    associated=associated,total=total,associated_pct=100*associated/total,
                    added_points=sum(int(r['added_points']) for r in rr),
                    improved_over_25m=int((delta<-25).sum()),worsened_over_25m=int((delta>25).sum())))
    write(ROOT/'subset-statistics.json',dict(rows=results,truth_used_only_after_inference_seal=True))
    with (ROOT/'subset-statistics.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]));writer.writeheader();writer.writerows(results)
    print(json.dumps([r for r in results if r['arm']=='fitted_c'],indent=2))

if __name__=='__main__':main()
