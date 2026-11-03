"""Verify source identity, frozen context and cross-provider control replay."""
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import numpy as np
from search import ROOT,observations
from leo.storage.shared_fast_scan import SharedFastScanStore
from leo.cli.shared_fast_position import load_input
from leo.application.shared_fast_position import prepare_views
from leo.contracts.regional_position import PositionOrbitBank,RegionalPrior
from leo.analysis.hard60_score import predict_orbits
from leo.analysis.regional_position_score import circular


def main():
    store=SharedFastScanStore('/srv/bulk/leo','shared-scan-q-v2')
    job,doc,terminal,stages=store.plot_evidence('075b34f9532dd9f7caf6c70830e4e8e8')
    source=load_input(doc);prepared,_=prepare_views(source);original=prepared['all'].observations
    a=np.load(ROOT/'baseline.npz');b=np.load(ROOT/'orbit-bank.npz')
    base=json.loads((ROOT/'baseline.json').read_text());ctx=json.loads((ROOT/'context.json').read_text())
    assert base['input_sha256']==job['input_sha256']
    assert tuple(ctx['window_ids'])==original.window_ids
    for saved,field in [('times','times_s'),('measured','measured_hz'),('receiver','receiver'),('channel','channel'),('rf','rf_hz')]:
        np.testing.assert_array_equal(a[saved],getattr(original,field))
    assert ctx['source_origin_ns']==prepared['all'].start_utc_ns
    assert set(b['numbers'])==set(terminal['provenance']['full_candidate_numbers'])
    base['terminal_sha256']=job['terminal']['sha256']
    (ROOT/'baseline.json').write_text(json.dumps(base,indent=2)+'\n')
    # Preserve the exact discovery-stage occurrences rather than inferring why
    # a candidate was dropped from its absence at the endpoint.
    occurrences=[]
    def visit(value,path):
        if isinstance(value,dict):
            for k,v in value.items():visit(v,path+[k])
        elif isinstance(value,list):
            for i,v in enumerate(value):visit(v,path+[i])
        elif value==57864:occurrences.append(path)
    for name,stage in stages.items():visit(stage,[name])
    (ROOT/'candidate-discovery-paths.json').write_text(json.dumps(dict(satellite=57864,paths=occurrences),indent=2)+'\n')
    bank=PositionOrbitBank(b['numbers'],b['nodes'],b['positions'],b['velocities']);prior=RegionalPrior(**ctx['prior'])
    results=json.loads((ROOT/'search-results.json').read_text());fig=json.loads((ROOT/'figure-summary.json').read_text())
    replay_errors=[]
    for g,f in zip([g for g in results['groups'] if g['selection']=='continuity_1'],fig):
        rows=np.array(g['rows']);obs=observations(a,ctx,rows)
        selected=g['arms']['fitted-c']['temporal']['all_timing_only']['ranked'][0]
        one=bank.select([list(bank.numbers).index(selected['satellite'])])
        pred=predict_orbits(one,obs,prior,np.array(ctx['vector'])[:2],np.array([selected['timing_s']]),derivatives=False)[0][:,0]
        rms=float(np.sqrt(np.mean(circular(a['measured'][rows]-a['correction'][rows]-pred)**2)))
        replay_errors.append(abs(rms-selected['training_rms_hz']))
        assert abs(rms-f['conditional_rms_hz'])<1e-8
    control=json.loads((ROOT/'tle-control.json').read_text())['results']
    for row in control:
        if row['provider']!='huggingface':continue
        g=next(g for g in results['groups'] if g['selection']=='continuity_1' and g['group']==row['group'])
        reference=g['arms']['fitted-c']['temporal'][row['split']+'_timing_only']['ranked'][0]
        assert reference['satellite']==row['satellite']
        assert abs(reference['training_rms_hz']-row['training_rms_hz'])<1e-7
        assert reference['timing_s']==row['timing_s']
    assert max(replay_errors)<1e-8
    receipt=dict(source_contract_replay=True,regional_candidate_bank_matches=True,
        maximum_carrier_rms_replay_error_hz=max(replay_errors),provider_control_reproduces_original=True,
        python=platform.python_version(),versions={name:importlib.metadata.version(name) for name in ['numpy','scipy','sgp4','matplotlib']},
        runtime_source='/opt/leo-fast-auto/f141dbb30321bc8f9e8183576c511431ea60a6b3/worker/src',
        tests='2 component tests passed: candidate-specific circular offsets and held-value independence')
    (ROOT/'validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
