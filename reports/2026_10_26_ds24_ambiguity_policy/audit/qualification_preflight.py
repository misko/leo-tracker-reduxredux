"""Independent four-owner source/prior/necessary-gate preflight."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parent.parent
SCI=ROOT/'qualification'
sys.path.insert(0,str(SCI))
import qualify as q
from ds23_new_family_prediction import new_gates

read=lambda p:json.loads(Path(p).read_bytes())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    start=time.monotonic();checks=[]
    def check(name,passed,**detail):checks.append(dict(name=name,passed=bool(passed),**detail))
    protocol=read(SCI/'protocol.json');digest=sha(SCI/'protocol.json')
    check('exact final scientific source and actual prior input bindings',
        digest=='af8700aab11de54c900ea8cd204c3487c5b64a5c71227bd9503a18aa5deb00d2' and
        all(sha(path)==value for path,value in protocol['source_input_hashes'].items()),bindings=len(protocol['source_input_hashes']))
    original=read(q.PRIOR/'protocol.json')['source_and_input_bindings']
    meta=read(SCI/'metadata.json');inv=read(q.PRIOR/'inventory.json');selected=read(q.PRIOR/'results.json')['selection']
    check('exact frozen chronological four whole owners and original canonical failures retained',
        [r['case'] for r in protocol['targets']]==['DS24-0014','DS24-0015','DS24-0016','DS24-0017'] and
        [r['candidate_norad'] for r in protocol['targets']]==[59733,68904,59786,100180] and
        [r['points'] for r in protocol['targets']]==[87,29,40,51] and
        [r['archived_nomination_compatible'] for r in meta['targets']]==[False,False,True,False] and
        [r['component'] for r in protocol['targets']]==[r['component'] for r in selected])
    for target in protocol['targets']:
        case=target['case'];row=next(r for r in inv['sources'] if r['case']==case and r['component']==target['component'])
        coverage=read(q.PRIOR/'ownership'/case/'parent.json')['coverage']
        paths=[q.r.SOURCE/'causal_prior'/case/name for name in ['previous.tle','receipt.json','previous_receipt.json']]
        check(case+': complete native IDs/nonoverlap and original causal phase/shape prior bytes',
            target['observation_ids']==row['observation_ids'] and len(set(target['observation_ids']))==target['points'] and
            all(not set(target['observation_ids'])&set(coverage[a]['accepted_observation_ids']) for a in q.ARMS) and
            all(str(path) in protocol['source_input_hashes'] and protocol['source_input_hashes'][str(path)]==original[str(path)] for path in paths))
        witness=meta['witness_availability'][case]
        check(case+': metadata-only witness availability never corroboration',
            witness['selection_independent_of_candidate_columns'] and not witness['same_family_validated'] and not witness['scored_in_this_branch'] and
            all(not any(k in r for k in ['candidate_index','candidate_norad','alias','rms_hz']) for r in witness['all_other_owner_metadata']))
    prep=read(SCI/'preparation.json')
    check('all eight actual parent/redacted response ports pass before any ordinary screen',
        len(prep['actual_contexts'])==4 and prep['no_new_scores'] and all(
            set(r['checks'])==set(q.ARMS) and all(a['hard_parent'] and a['original_remaining_gates_pass'] and
                max(a['redaction'].values())<1e-8 for a in r['checks'].values()) for r in prep['actual_contexts']) and
        not (SCI/'execution_started.json').exists())
    def funcs(path):return {n.name:ast.dump(n) for n in ast.parse(Path(path).read_text()).body if isinstance(n,ast.FunctionDef)}
    before,after=funcs(SCI/'preparation01/qualify.py'),funcs(SCI/'qualify.py')
    check('narrow prior-binding correction did not alter actual smoke/scoring/gate ports',
        all(before[name]==after[name] for name in before if name!='prepare') and
        sha(SCI/'preparation01/protocol.json')=='1935c2361611f23c462e06218fc4dbd0cd1185f81c9b41d18ee5e4fd2569c4f3')
    status=pytest.main(['-q','-p','no:cacheprovider',str(SCI/'test_qualification.py')])
    check('four owned mode,alias,metadata and actual ordinary-screen-to-MAP ports rerun',status==0)
    # Compare the adapter directly with the original existing new-family gate.
    times=np.linspace(0.,35.,31);white=(np.eye(31)/150.,0.);elevation=np.ones(31)
    for name,raw,el in [('smooth',20*np.sin(times),elevation),('alias',20*np.sin(times)+q.k.PERIOD,elevation),
        ('slope',np.linspace(-2000,2000,31),elevation),('invisible',np.zeros(31),-elevation)]:
        track=dict(times=times)
        entry=dict(component='fixture',track_index=0,norad=1,candidate_index=0,points=31,observation_ids=[str(i) for i in range(31)])
        p=SimpleNamespace(scan=SimpleNamespace(tracks=[track],white=[white]),new_entries=[entry],new_slices=[slice(0,31)],
            calculate=lambda x:dict(new_raw_prediction_residual_hz=raw,new_prediction_elevation=el))
        actual=new_gates(p,np.zeros(2))[0];adapter=q.adequacy.source_gate(raw,times,white,el)
        check(name+': adequacy is exactly existing new_gates necessary comparator',
            actual['compatible']==adapter['compatible'] and actual['rms_hz']==adapter['rms_hz'] and actual['bias_hz']==adapter['bias_hz'])
    check('matched same-pool covariance/alias law, bounded denominator and no admission/fits frozen',
        protocol['maximum_owner_arm_slots']==8 and protocol['maximum_physical_candidate_slots']==64 and
        protocol['workers']==2 and protocol['BLAS_threads']==1 and protocol['cap_worker_seconds']==600 and
        protocol['no_position_fits'] and protocol['no_GPS_or_new_RF'] and protocol['metadata_witness_not_counted_as_support'] and
        protocol['qualified_new_identity_requires_original_support_and_shared_hierarchy'])
    check('immutable sources/inputs after independent pure gate tests',
        all(sha(path)==value for path,value in protocol['source_input_hashes'].items()))
    result=dict(all_passed=all(r['passed'] for r in checks),protocol_sha256=digest,checks=checks,
        seconds=time.monotonic()-start,source_sha256=sha(__file__),new_orbit_propagation_calls=0,
        real_target_evidence_integrals=0,position_fits=0,geographic_truth_read=False,
        scope='Cavity ordering and necessary whole-source gates only; no calibrated identity probability or admission.')
    with (ROOT/'audit/qualification_preflight.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(all_passed=result['all_passed'],checks=len(checks),seconds=result['seconds'],failed=[r for r in checks if not r['passed']])))


if __name__=='__main__':main()
