"""Independent direct category-probability replay, before report-only GPS use."""

import argparse
import math

from probe_ds23_unknown_catalogue_prior import OUT, ORIGINAL, prepare
from run_algo01_ds23_sample import ROOT, read, write, sha


def verify():
    protocol=prepare();path=OUT/'decisions.json';decisions=read(path)
    if sha(ORIGINAL/'cohort_verification.json')!=protocol['RF_verification_sha256']:
        raise ValueError('independent original RF audit changed')
    if not decisions['all_terminal'] or len(decisions['rows'])!=40:
        raise ValueError('incomplete decisions')
    rows=[]
    for d in decisions['rows']:
        original_path=ORIGINAL/d['case']/'result.json'
        if sha(original_path)!=d['original_result_sha256']:
            raise ValueError('numerical fit changed')
        record=read(original_path);screen=read(ORIGINAL/d['case']/'screen.json')
        n=d['catalogue_count'];families=len(screen['ledger'])
        baseline_log_prior=families*math.log(.95/n)
        candidates=[];errors=[]
        for decision,t in zip(d['trials'],record['trials'][1:],strict=True):
            k=len(t['unknown_families'])
            alternative_log_prior=(families-k)*math.log(.95/n)+k*math.log(.05)
            relative_code=-2*(alternative_log_prior-baseline_log_prior)
            old_relative_code=2*k*math.log(.95/.05)
            costs={a:t['arms'][a]['negative_twice_elbo']-old_relative_code+relative_code for a in ('c0','fitted_c')}
            differences=[costs[a]-decision['catalogue_costs'][a] for a in costs]
            errors.extend(differences)
            gains={a:record['reference_costs'][a]-costs[a] for a in costs}
            eligible=t['paired_valid'] and min(gains.values())>2*math.log(2)
            if eligible!=decision['eligible'] or max(map(abs,differences))>1e-8:
                raise ValueError('normalized category prior or eligibility changed')
            if eligible:candidates.append(decision)
        chosen=min(candidates,key=lambda t:t['catalogue_costs']['c0']) if candidates else None
        if d['accepted']!=(chosen is not None) or d['selected_trial_index']!=(chosen['original_trial_index'] if chosen else None):
            raise ValueError('selected hypothesis changed')
        rows.append(dict(case=d['case'],catalogue_count=n,maximum_cost_difference=max(map(abs,errors)),accepted=d['accepted']))
    write(OUT/'verification.json',dict(qualified=True,all_terminal=True,count=len(rows),rows=rows,
        decisions_sha256=sha(path),RF_verification_sha256=protocol['RF_verification_sha256'],
        normalized_prior_reconstructed_directly_from_probabilities=True,no_GPS_used=True,
        source_sha256=sha(ROOT/'tools/verify_ds23_unknown_catalogue_prior.py')))
    print('Verified exact catalogue-prior changes',len(rows),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('verify','evaluate'),required=True)
    stage=parser.parse_args().stage
    if stage=='verify':verify()
    else:
        audit=read(OUT/'verification.json')
        if not audit['qualified'] or audit['decisions_sha256']!=sha(OUT/'decisions.json'):
            raise ValueError('decisions must be independently verified before GPS evaluation')
        from probe_ds23_unknown_catalogue_prior import evaluate
        evaluate()
