"""Descriptive residual correlation with measured nearest-time pairs only."""
from collections import defaultdict
from itertools import combinations
import csv
import numpy as np
from audit_evidence import OUT,read,write,summary

def main():
    lanes=defaultdict(list)
    with (OUT/'curved_point_residuals.csv').open() as f:
        for r in csv.DictReader(f):
            if r['group']!='all_channels':continue
            key=(r['case'],r['arm'],int(r['norad']),int(r['receiver']),int(r['channel']))
            lanes[key].append((float(r['time_s']),float(r['residual_hz'])))
    data={k:np.array(sorted(v)) for k,v in lanes.items()}
    rows=[]
    for case in read(OUT/'evidence_quick.json')['cases']:
        for arm in ('c0','fitted_c'):
            keys=[k for k in data if k[:2]==(case,arm)]
            for ka,kb in combinations(keys,2):
                same_family=ka[2]==kb[2];same_rx=ka[3]==kb[3];same_band=(ka[4]<=4)==(kb[4]<=4)
                if same_family and not same_rx and same_band:kind='same_family_cross_RX_same_band'
                elif not same_family and same_rx and same_band:kind='cross_family_same_RX_same_band'
                elif not same_family and same_rx and not same_band:kind='cross_family_same_RX_cross_band'
                else:continue
                a,b=data[ka],data[kb]
                if min(a[-1,0],b[-1,0])-max(a[0,0],b[0,0])<1:continue
                ii,jj=np.where(abs(a[:,0,None]-b[None,:,0])<=.5)
                if len(ii)<6:continue
                order=np.argsort(abs(a[ii,0]-b[jj,0]),kind='stable');used_a=set();used_b=set();ia=[];ib=[]
                for ix in order:
                    i,j=int(ii[ix]),int(jj[ix])
                    if i in used_a or j in used_b:continue
                    used_a.add(i);used_b.add(j);ia.append(i);ib.append(j)
                if len(ia)<6:continue
                aa,bb=a[ia,1],b[ib,1]
                if np.std(aa)==0 or np.std(bb)==0:continue
                rows.append(dict(case=case,arm=arm,kind=kind,left=ka[2:],right=kb[2:],pairs=len(ia),correlation=float(np.corrcoef(aa,bb)[0,1])))
    stats={}
    for arm in ('c0','fitted_c'):
        for kind in ('same_family_cross_RX_same_band','cross_family_same_RX_same_band','cross_family_same_RX_cross_band'):
            rr=[r for r in rows if r['arm']==arm and r['kind']==kind]
            scanmedians=[np.median([r['correlation'] for r in rr if r['case']==case]) for case in sorted({r['case'] for r in rr})]
            stats[arm+'/'+kind]=dict(track_pair_correlations=summary([r['correlation'] for r in rr]),median_per_scan_correlation=summary(scanmedians),measured_time_pairs=sum(r['pairs'] for r in rr))
    write(OUT/'residual_correlations.json',dict(rows=rows,summary=stats,
        method='All retained curved points merged by model family/RX/channel; nearest-distance-first unique measured pairs within0.5s, at least6pairs. No interpolation. Pearson within matched pair.',
        conditional_postfit_only=True,descriptive_dependent_pairs_not_identity_or_causality=True))
    print(stats)

if __name__=='__main__':main()
