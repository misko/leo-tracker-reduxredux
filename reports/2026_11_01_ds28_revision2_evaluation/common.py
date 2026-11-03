"""DS28 bookkeeping over the unchanged, previously evaluated recovery model."""
from pathlib import Path
import importlib.util,json,gzip,hashlib,copy,os
import numpy as np
ROOT=Path(__file__).resolve().parent
PREVIOUS=ROOT.parent/'2026_11_01_ds26_ds27_causal_variants'
RELEASE=Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
WORK=Path('/srv/bulk/leo/research/ds28-r2-causal-variants-20261101')
INVENTORY=ROOT/'residuals'
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
prior=module('previous_recovery_common',PREVIOUS/'common.py')
read,write,digest=prior.read,prior.write,prior.digest
ARMS,POLICIES,reconstruct=prior.ARMS,prior.POLICIES,prior.reconstruct

def prepare():
    from leo.contracts.fast_graph_position_v4 import validate_terminal,owners,incumbent_proof
    rank=module('ds28_rank',RELEASE/'reports/2026_10_31_algo05_promotion/reproduction/rank_native_residuals.py')
    cohort=[];unavailable=[];summaries=[];fragments=[]
    availability={r['case']:r for r in read(ROOT/'input-availability.json')['rows']}
    for row in read(ROOT/'baseline-roster.json')['cases']:
        case=row['case'];folder=WORK/'baselines'/case
        if row['state']!='ready':
            a=availability[case]
            reason=a.get('reason') or ('upstream_ALGO02_'+a.get('state','unavailable'))
            unavailable.append(dict(row,reason=reason,public_input=a));continue
        t=read(folder/'terminal.json');validate_terminal(t,input_sha256=t['input_sha256'])
        old=t['incumbent'];proof=incumbent_proof(old)
        current=folder/'current';paths=list((current/'all-large-track-recovery').glob('*/inventory.json'))
        if len(paths)!=1:raise ValueError('Exactly one native inventory required')
        invpath=paths[0];inv=read(invpath);native=Path(inv['job']['root'])/inv['job']['case']
        obs=read(native/'observations.json');tracks=read(native/'tracks.json')
        published_owners=owners(old);arms=proof['selected']['arms'] if proof.get('selected') else proof['baseline']['arms']
        # Selected ALGO04 proofs are mapped using the verified relocation receipt.
        sel=copy.deepcopy(proof.get('selected'))
        if sel:
            candidates=[read(p).get('selected') for p in (current/'decision.json',current/'cache/decision.json') if p.exists()]
            matches=[v for v in candidates if v and v['kind']==sel['kind'] and all(v['arms'][a]['endpoint_east_north_km']==arms[a]['endpoint_east_north_km'] for a in ARMS)]
            local=matches[0] if matches else None
            if local is None:
                raise ValueError('Published selected proof differs from relocated decision')
            sel=local
        gap=None
        if t['candidate']:
            gap=read(folder/'decision.json')['selected'];arms=read(Path(gap['path'])/'target_0.json')['arms']
            published_owners={a:arms[a]['proposed_owners'] for a in ARMS}
        local,summary=rank.fragment_rows(case,tracks,obs,published_owners['fitted_c'],inv['job']['identities'])
        summaries.append(summary);fragments+=local
        eligible=[r for r in local if r['points']>=20 and r['duration_s']>=15 and
                  not set(r['observation_ids'])&(set(published_owners['c0'])|set(published_owners['fitted_c']))]
        eligible.sort(key=lambda r:(-r['duration_s'],-r['points'],r['fragment_id']))
        z=dict(case=case,inventory_path=str(invpath),recovery_path=str(current),native_path=str(native),
               scan_receipt=read(native/'receipt.json'),selected=sel,gap_selected=gap,baseline_arms=arms,
               baseline_owners=published_owners,baseline_source=str(folder/'terminal.json'),baseline_sha256=digest(folder/'terminal.json'),
               targets=eligible[:3],eligible_targets=len(eligible))
        write(ROOT/'inputs'/(case+'.json'),z)
        cohort.append(dict(case=case,targets=len(z['targets']),eligible_targets=len(eligible),
                           cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],origin_utc_ns=z['scan_receipt']['origin_utc_ns']))
    protocol=copy.deepcopy(read(PREVIOUS/'protocol.json'))
    protocol.update(cohort=cohort,unavailable=unavailable,parent_experiment=str(PREVIOUS),
                    parent_protocol_sha256=digest(PREVIOUS/'protocol.json'),dataset_manifest_sha256=digest(ROOT/'dataset/manifest.json'),
                    reuse='Exact public ALGO04 exports; fresh installed ALGO05 recovery; unchanged research variants',
                    evaluation_site_used_for_inference=False)
    write(ROOT/'protocol.json',protocol);write(INVENTORY/'per-scan.json',summaries)
    with gzip.open(INVENTORY/'all-residual-fragments.json.gz','wt') as f:json.dump(fragments,f)
    print('Prepared',len(cohort),'scans',sum(c['targets'] for c in cohort),'targets',flush=True)

if __name__=='__main__':prepare()
