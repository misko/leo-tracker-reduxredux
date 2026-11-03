"""General 48/72h age and 15/35s phase 2x2 diagnostic, fixed published endpoints."""
import argparse
from pathlib import Path
import numpy as np
from sgp4.api import Satrec
import investigate as base
from leo.sky.propagation import ElementSetCatalogue


def run(out,case):
    sources=[r for r in base.read(out/'targets.json') if r['case']==case]
    receipt=base.read(out/'cases'/case/'receipt.json');meta=receipt['scan_receipt'];records=base.read(out/'causal72.json')['scans'][case]['elements']
    numbers=np.array(list(map(int,records)));sats=tuple(Satrec.twoline2rv(*records[str(n)]['lines']) for n in numbers)
    cat=ElementSetCatalogue(tuple(map(str,numbers)),tuple(map(int,numbers)),sats);grid=np.arange(-40.,341.)
    p,v,good=base.ecef_states(cat,meta['origin_utc_ns'],grid)
    failures=numbers[~good].tolist();numbers=numbers[good]
    bank=dict(time_s=grid,position_km=p[good],velocity_km_s=v[good]);lookup={int(n):j for j,n in enumerate(numbers)}
    age={int(n):(meta['cutoff_utc_ns']-records[str(n)]['element_epoch_utc_ns'])/3600e9 for n in numbers}
    result=[]
    for row in sources:
        d=base.read(out/'cases'/case/(row['fragment_id']+'.json'));t=np.array(d['times_s']);q=row['rf_hz']/11.5e9;offers={}
        for bound in (15,35):
            base.PHASES=np.arange(-bound,bound+.01,2.)
            for arm in base.ARMS:
                offers[f'{bound}_{arm}']=base.coarse(bank,numbers,t,np.array(d['corrected_hz'][arm]),receipt['positions'][arm],q)
        finalists=sorted(set(d['finalists'])|{v['norad'] for offer in offers.values() for values in offer.values() for v in values})
        fits=[]
        for bound in (15.,35.):
            for arm in base.ARMS:
                for n in finalists:
                    if n not in lookup:continue
                    for model in ('phase_offset','phase_small_rate'):
                        f=base.exact(bank,lookup[n],n,t,np.array(d['corrected_hz'][arm]),receipt['positions'][arm],q,model,phase_limit=bound)
                        fits.append(dict(arm=arm,phase_limit_s=bound,age_hours=age[n],**f))
        summaries=[]
        for hours in (48,72):
            for bound in (15.,35.):
                for arm in base.ARMS:
                    for model in ('phase_offset','phase_small_rate'):
                        ff=sorted([r for r in fits if r['age_hours']<=hours and r['phase_limit_s']==bound and r['arm']==arm and r['model']==model],key=lambda r:r['cost'])
                        summaries.append(dict(age_limit_h=hours,phase_limit_s=bound,arm=arm,model=model,best=ff[0],runner_up=ff[1],score_margin=ff[1]['cost']-ff[0]['cost']))
        result.append(dict(source=row,full_catalogue_count=len(numbers),propagation_failure_norads=failures,eligible_48h_count=sum(a<=48 for a in age.values()),offers=offers,finalists=finalists,summaries=summaries,
                           policy='general 72-hour causal catalogue, no truth or NORAD whitelist; 2x2 age and phase bounds; frozen inherited radio model and published position; coarse shortlist then exact full-point fits; not production acceptance'))
    base.write(out/'cases'/case/'expanded_search.json',result)
    print(case,'expanded search complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('case');a=p.parse_args();run(a.output,a.case)
