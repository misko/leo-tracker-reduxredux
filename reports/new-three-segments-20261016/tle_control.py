"""Same three shortlisted IDs/site/calibration and timing budget, two causal TLEs."""
import json
from pathlib import Path
import numpy as np
from search import ROOT,observations
from leo.contracts.regional_position import RegionalPrior
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def main():
    a=np.load(ROOT/'baseline.npz');ctx=json.loads((ROOT/'context.json').read_text())
    result=json.loads((ROOT/'search-results.json').read_text())
    groups=[g for g in result['groups'] if g['selection']=='continuity_1']
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector'])
    output=[]
    extent=observations(a,ctx,np.arange(len(a['times'])))
    for provider in ['huggingface','space-track']:
        snap=archive.select_latest_before(ctx['source_origin_ns'],provider)
        cat=parse_element_sets(archive.read(snap));look={int(n):i for i,n in enumerate(cat.satellite_numbers)}
        nums=[66854,58362,57864]
        bank,_=build_regional_bank(cat,[look[n] for n in nums],ctx['source_origin_ns'],extent,prior)
        for g,num in zip(groups,nums):
            rows=np.array(g['rows']);obs=observations(a,ctx,rows);one=bank.select([list(bank.numbers).index(num)])
            y=a['measured'][rows]-a['correction'][rows];train=obs.times_s<=np.median(obs.times_s)
            masks={'all':np.ones(len(rows),bool),'early_to_late':train,'late_to_early':~train}
            best={key:(float('inf'),None) for key in masks}
            for shift in np.linspace(-5,5,201):
                pred,vis,_,_=predict_orbits(one,obs,prior,v[:2],np.array([shift]),derivatives=False)
                r=circular(y-pred[:,0])
                for split,mask in masks.items():
                    score=float(np.sum((r[mask]/125)**2)+(shift/2)**2) if vis[mask].all() else float('inf')
                    if score<best[split][0]:
                        best[split]=(score,dict(provider=provider,snapshot_sha256=snap.digest,group=g['group'],
                            satellite=num,split=split,timing_s=float(shift),
                            training_rms_hz=float(np.sqrt(np.mean(r[mask]**2))),
                            test_rms_hz=float(np.sqrt(np.mean(r[~mask]**2))) if (~mask).any() else None))
            output.extend(item[1] for item in best.values())
    document=dict(qualification='Conditional shortlisted-ID test only: same original position/calibration, '
        'three candidate identities, timing grid and prior for both causal providers. Each provider '
        'uses its latest snapshot collected before the scan; element ages are reported separately '
        'in details.json. Not a fresh discovery/localization run or independent identity validation.',results=output)
    (ROOT/'tle-control.json').write_text(json.dumps(document,indent=2)+'\n')
    print(json.dumps(document,indent=2),flush=True)


if __name__=='__main__':main()
