"""Predeclared hardware-dependent control; choose no branch using geography.

Earlier additive-Hz controls failed on the original development scans. This
control tests only the newly distinguished multi-LO geometry, conditional on
the recorded mapping. It does not replace the original fixed-LNB primary test.
"""

import argparse
import numpy as np

from probe_ds23_converter_drift import OUT,prepare,ARMS
from run_algo01_ds23_sample import ROOT,read,write,sha


def seal():
    source=Path(__file__)
    protocol=prepare();path=OUT/'variable_LO_protocol.json'
    if path.exists():
        old=read(path)
        if old['source_sha256']!=sha(source):raise ValueError('supplemental control source changed')
        return old
    if (OUT/'evaluation.json').exists():raise ValueError('must seal hardware-dependent policy before new position errors are evaluated')
    rows=[]
    for case in protocol['development_cases']+protocol['confirmation_cases']:
        geometry=read(OUT/(case+'_converter.json'))['geometry']
        result=read(OUT/(case+'_result.json'))
        variable=len({t['lnb_lo_hz'] for t in geometry['targets']})>1
        adopt=bool(variable and result['methods']['LNB']['accepted'])
        rows.append(dict(case=case,variable_configured_LO=variable,adopt_LNB=adopt,
            result_sha256=sha(OUT/(case+'_result.json'))))
    saved=dict(source_sha256=sha(source),rows=rows,decision_inputs='recorded converter references and original paired residual gates only',
        policy='fixed LNB law when configured targets have multiple distinct LNB references and both c arms pass; exact incumbent otherwise',
        new_position_errors_not_evaluated_at_seal=True,original_primary_test_unchanged=True,
        prior_evidence='earlier additive-Hz frequency-law experiment on original20 failed mean/median; multi-LO mapping is the new distinction',
        secondary_prespecified_before_first_geographic_score=True,no_GPS_or_new_RF_used=True,
        success='whole-cohort fitted-c mean AND median improve in BOTH development and confirmation; do not score only the multi-LO subset')
    write(path,saved);print('Sealed variable-LO control before geographic evaluation',sum(r['adopt_LNB'] for r in rows),'adoptions',flush=True)
    return saved


def evaluate():
    supplemental=seal();protocol=prepare();audit=read(OUT/'cohort_verification.json')
    if not audit['qualified'] or len(audit['receipts'])!=40:raise ValueError('all RF replays required')
    from report_algo02_ds23 import position_error
    rows=[];summary={}
    for cohort in ('development','confirmation'):
        summary[cohort]={}
        for arm in ARMS:
            before=[];after=[]
            for decision in supplemental['rows']:
                case=decision['case']
                if case not in protocol[cohort+'_cases']:continue
                path=OUT/(case+'_result.json')
                if sha(path)!=decision['result_sha256']:raise ValueError('sealed supplemental result changed')
                r=read(path);old=r['incumbent_arms'][arm]
                chosen=r['methods']['LNB']['arms'][arm] if decision['adopt_LNB'] else old
                a=position_error(old['endpoint_latlon']);b=position_error(chosen['endpoint_latlon'])
                before.append(a);after.append(b)
                rows.append(dict(case=case,cohort=cohort,arm=arm,adopted=decision['adopt_LNB'],
                    incumbent_error_km=a,policy_error_km=b))
            summary[cohort][arm]=dict(incumbent_mean_km=float(np.mean(before)),incumbent_median_km=float(np.median(before)),
                policy_mean_km=float(np.mean(after)),policy_median_km=float(np.median(after)),
                mean_and_median_improve=bool(np.mean(after)<np.mean(before) and np.median(after)<np.median(before)))
    success=all(summary[c]['fitted_c']['mean_and_median_improve'] for c in summary)
    write(OUT/'variable_LO_evaluation.json',dict(summary=summary,success=success,rows=rows,
        protocol_sha256=sha(OUT/'variable_LO_protocol.json'),GPS_used_only_here=True,
        goal_population=413,goal_achieved=False,original_primary_unchanged=True))
    print('Variable-LO supplemental confirmed',success,summary,flush=True)


if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=('seal','evaluate'),required=True)
    seal() if parser.parse_args().stage=='seal' else evaluate()
