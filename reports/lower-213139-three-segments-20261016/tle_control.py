"""Compare causal element providers on fixed inspected track/candidate pairs."""
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from search import ROOT,observations,offset_fit
from leo.contracts.regional_position import RegionalPrior
from leo.analysis.regional_position_bank import build_regional_bank
from leo.analysis.regional_position_score import circular
from leo.analysis.hard60_score import predict_orbits
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_sets


def main():
    a=np.load(ROOT/'baseline.npz');ctx=json.loads((ROOT/'context.json').read_text())
    base=json.loads((ROOT/'baseline.json').read_text());shape=json.loads((ROOT/'shape-controls.json').read_text())
    groups=[g for g in shape['groups'] if g['part']==0];prior=RegionalPrior(**ctx['prior']);v=np.array(ctx['vector'])
    archive=TleArchiveReader(Path('/var/lib/leo/tle'));origin=ctx['source_origin_ns'];fmt=lambda t:datetime.fromtimestamp(t/1e9,timezone.utc).isoformat()
    output=[];comparisons=[]
    pairs=[[66544],[60127],[67704]]
    nums=sorted(set(n for group in pairs for n in group));extent=observations(a,ctx,np.arange(len(a['times'])))
    for provider in ['space-track','huggingface']:
        snap=archive.select_latest_before(origin,provider);cat=parse_element_sets(archive.read(snap));epochs=cat.element_epoch_utc_ns()
        look={int(n):j for j,n in enumerate(cat.satellite_numbers)}
        bank,_=build_regional_bank(cat,[look[n] for n in nums],origin,extent,prior)
        output.append(dict(provider=provider,collected_utc=fmt(snap.collected_utc_ns),digest=snap.digest,
            same_payload_as_saved=snap.digest==base['snapshot_sha256'],collection_age_minutes=(origin-snap.collected_utc_ns)/6e10,
            candidate_ages=[dict(satellite=num,element_age_hours=(origin-epochs[look[num]])/3.6e12) for num in nums]))
        for group,ids in zip(groups,pairs):
            rows=np.array(group['rows']);obs=observations(a,ctx,rows);small=bank.select([list(bank.numbers).index(num) for num in ids])
            yy=a['measured'][rows]-a['correction'][rows];train=obs.times_s<=np.median(obs.times_s)
            masks={'all':np.ones(len(rows),bool),'early_to_late':train,'late_to_early':~train}
            state={split:dict(score=np.full(len(ids),np.inf),rms=np.zeros(len(ids)),held=np.zeros(len(ids)),
                shift=np.zeros(len(ids)),offset=np.zeros(len(ids))) for split in masks}
            for shift in np.linspace(-20,20,401):
                pred,vis,_,_=predict_orbits(small,obs,prior,v[:2],np.full(len(ids),shift),derivatives=False)
                residual=circular(yy[:,None]-pred)
                for split,mask in masks.items():
                    off,tr,te=offset_fit(residual,mask);score=mask.sum()*(tr/125)**2+(shift/2)**2
                    score[~vis[mask].all(axis=0)]=np.inf;s=state[split];take=score<s['score']
                    for key,val in [('score',score),('rms',tr),('held',te),('offset',off)]:s[key][take]=val[take]
                    s['shift'][take]=shift
            for split,s in state.items():
                for j,num in enumerate(ids):
                    comparisons.append(dict(provider=provider,group=group['group'],satellite=num,split=split,
                        timing_s=float(s['shift'][j]),offset_hz=float(s['offset'][j]),
                        training_rms_hz=float(s['rms'][j]),test_rms_hz=float(s['held'][j]) if (~masks[split]).any() else None))
    doc=dict(providers=output,comparisons=comparisons,qualification='Latest snapshots collected before '
        'the recording, same shortlisted candidate identities, frozen original site/calibration, same '
        'observations, offset/timing family, priors and search budget. Not a full new provider pipeline run.')
    (ROOT/'tle-control.json').write_text(json.dumps(doc,indent=2)+'\n')
    print(json.dumps(dict(providers=output,all=[r for r in comparisons if r['split']=='all']),indent=2),flush=True)


if __name__=='__main__':main()
