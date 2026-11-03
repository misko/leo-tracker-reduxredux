"""Replay saved calibration components and expose their measured effects."""
import json
from pathlib import Path
import numpy as np
from search import ROOT
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.application.shared_orbit_replay import selected_model
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior


def main():
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2')
    job,doc,terminal,stages=store.plot_evidence('73c4b28b4f002e0d2154bab2f67457b6')
    source=load_input(doc);prepared,nodes=prepare_views(source);obs=prepared['all'].observations
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);look={int(n):j for j,n in enumerate(bank.numbers)}
    nums=terminal['candidate_numbers'];selected=bank.select([look[n] for n in nums])
    prior=RegionalPrior(**terminal['provenance']['prior'])
    model,fit,audit=selected_model(prepared,selected,prior,nodes,terminal,stages)
    v,n=(np.array(fit[k]) for k in ['vector','nuisance'])
    ev,details=model.evaluate_details(v,n)
    correction=model.original.correction(v,n[:model.clock_count])
    np.testing.assert_array_equal(obs.times_s,a['times'])
    np.testing.assert_allclose(correction,a['correction'],atol=1e-8,rtol=0)
    no_clock=model.original.correction(v,np.zeros(model.clock_count))
    no_drift=no_clock-v[3+2*obs.receiver]*(obs.times_s-obs.time_center_s)
    np.savez_compressed(ROOT/'calibration-components.npz',published=correction,no_clock=no_clock,
        no_clock_or_linear_drift=no_drift,raw=np.zeros(len(obs.times_s)))
    base=json.loads((ROOT/'baseline.json').read_text())
    summary=[]
    for group in base['groups']:
        rows=np.array(group['continuity_segments'][0]['rows']);t=obs.times_s[rows];x=t-t.mean()
        design=np.column_stack([np.ones(len(x)),x,x*x,x*x*x])
        record=dict(group=group['name'],clock_range_hz=float(np.ptp((correction-no_clock)[rows])),
            receiver_linear_drift_hz_s=float(v[3+2*(group['receiver']-1)]),polynomial_rms={})
        for key,cor in [('raw',np.zeros(len(correction))),('published',correction),('no_clock',no_clock)]:
            y=np.unwrap((obs.measured_hz[rows]-cor[rows])*2*np.pi/(1/4.4e-6))*(1/4.4e-6)/(2*np.pi)
            r=y-design@np.linalg.lstsq(design,y,rcond=None)[0]
            record['polynomial_rms'][key]=float(np.sqrt(np.mean(r*r)))
        summary.append(record)
    # Preserve discovery paths for every integer candidate. Avoid substring
    # searches, which also match digits inside floating point parameters.
    occurrences={}
    def visit(value,path):
        if isinstance(value,dict):
            for key,val in value.items():visit(val,path+[key])
        elif isinstance(value,list):
            for i,val in enumerate(value):visit(val,path+[i])
        elif isinstance(value,int) and value in look:
            occurrences.setdefault(str(value),[]).append(path)
    for key,stage in stages.items():visit(stage,[key])
    report=dict(audit=audit,source_sha256=job['input_sha256'],terminal_sha256=job['terminal']['sha256'],
        receiver_drifts_hz_s=[float(v[3]),float(v[5])],groups=summary,
        discovery_occurrences=occurrences,detection_probabilities={str(num):float(q) for num,q in zip(nums,details['detection_probability'])},
        runtime_source='/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src')
    (ROOT/'context-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:val for k,val in report.items() if k not in ['discovery_occurrences','detection_probabilities']},indent=2),flush=True)


if __name__=='__main__':main()
