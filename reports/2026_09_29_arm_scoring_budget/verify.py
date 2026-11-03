"""Independent reconstruction of the oracle diagnostic's recorded timings."""
import json
import math
from pathlib import Path
import sys
import hashlib

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_09_28_arm_full_optimization'))
import arm_cohort as a

def main():
    baseline=a.baseline(); results={}
    for version in ('run-v2','run-v3','run-v4'):
        folder=HERE/version; summary=json.loads((folder/'summary.json').read_text())
        assert summary['complete'] and len(summary['rows'])==12
        assert summary['baseline_sha256']==a.sha(a.BASELINE)
        receipt=json.loads((folder/'build-receipt.json').read_text())
        assert receipt['binary_sha256']==a.sha(folder/'build/probe')
        for name,digest in receipt['source_sha256'].items():
            assert a.sha(folder/'build'/name)==digest
        assert '-DLEO_FULL_ARM_AFFINITY' in receipt['command']
        totals=[]
        for saved in summary['rows']:
            i,rep=saved['case'],saved['repeat']; ctx=saved['context']
            probes=baseline[(ctx['session_id'],ctx['visit_index'])]
            rows=[json.loads(s) for s in (folder/f'case-{i}-r{rep}.jsonl').read_text().splitlines()]
            assert len(rows)==176
            expected={(w,rx,k) for w in range(11) for rx in range(2) for k in range(8)}
            seen=set(); positive=0; all_ms=0.; pos_ms=0.; ingestion={}; keys=set(); unique_pos_ms=0.
            for r in rows:
                key=r['window'],r['rx'],r['rank'];assert key not in seen;seen.add(key)
                assert all(math.isfinite(v) for v in r.values())
                c=probes[(r['rx'],r['window'])]['candidates'][r['rank']]
                assert r['epoch']==c['epoch_sample'] and r['cfo']==c['acquired_cfo_hz']
                assert abs(r['exact']-c['exact_score'])<2e-9
                assert abs(r['control']-c['control_score'])<2e-9
                assert abs(r['tracking_cfo']-c['tracking_cfo_hz'])<2e-6
                assert (r['exact']-r['control']>=.025)==(c['margin']>=.025)
                all_ms+=r['cpu_ms'];ingestion[key[:2]]=r['window_ingest_ms']
                if c['margin']>=.025:
                    positive+=1;pos_ms+=r['cpu_ms']
                    cachekey=(r['window'],r['rx'],r['epoch'],float(r['cfo']).hex())
                    if cachekey not in keys:unique_pos_ms+=r['cpu_ms'];keys.add(cachekey)
            assert seen==expected
            assert positive==saved['positive_candidates']
            assert abs(all_ms-saved['all_scoring_ms'])<1e-8
            assert abs(pos_ms-saved['oracle_positive_scoring_ms'])<1e-8
            ingest=sum(ingestion.values())+rows[0].get('dwell_convert_ms',0)
            assert abs(ingest-saved['ingest_ms'])<1e-8
            totals.append({'case':i,'repeat':rep,'positive_entries':positive,
                           'unique_positive_keys':len(keys),'unique_positive_scoring_ms':unique_pos_ms})
        results[version]={'verified_candidate_evaluations':2112,'unique_windows':88,
             'unique_positive_entries':sum(r['positive_entries'] for r in totals if r['repeat']==0),
             'mean_unique_positive_scoring_ms':sum(r['unique_positive_scoring_ms'] for r in totals)/12,
             'rows':totals}
    old=json.loads((HERE.parent/'2026_09_28_arm_boundary_fallback/arm-cohort-v1/manifest.json').read_text())['remote_directory']
    hashes={}
    for edge,templates in a.template_map().items():
        for kind,t in templates.items():
            digest=a.remote(f'sha256sum {old}/{edge}-{kind}.c128').split()[0]
            assert digest==t['sha256'];hashes[f'{edge}-{kind}']=digest
    result={'verified':True,'variants':results,'remote_template_sha256':hashes,
            'scope':'2.5 MS/s oracle-seeded scoring only; no deployable discovery or RF capture'}
    (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='rows'} for k,v in results.items()},indent=2))

if __name__=='__main__':main()
