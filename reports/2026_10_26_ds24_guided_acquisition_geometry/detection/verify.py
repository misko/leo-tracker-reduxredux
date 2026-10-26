"""Owned tests and artifact-only checks; no new IQ, fitting or detector calls."""
import inspect
import sys
import time
import unittest
from study import HERE,load,sha,write,old,donors,guide

began=time.monotonic()
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_*.py')
test=unittest.TextTestRunner(verbosity=2,stream=sys.stderr).run(suite)
p=load(HERE/'protocol.json');data=load(HERE/'recorded.json');pre=load(HERE/'preflight.json')
active=load(HERE/'active_null.json');noise=load(HERE/'noise_null.json')
checks=dict(tests_passed=test.wasSuccessful(),tests=test.testsRun,
    frozen_sources_unchanged=all(sha(path)==h for path,h in p['files'].items()),
    historical_runtime_unchanged=old.replay.runtime_identity()==p['identity'],
    all_eight_windows=len(data['rows'])==8 and all(s['status']=='complete'for s in data['rows']),
    original20ms_parity=all(all(v['all_passed']for v in s['receipt']['parity'].values())for s in data['rows']),
    split10ms_parity=all(s['public10ms_vs_unchanged_production_all_candidates_equal']for s in pre['split_parity']),
    expected_recorded_RX_scenarios=sum(len(v['outcomes'])for s in data['rows']for v in s['scenarios'].values())==64,
    active_null_trials=len(active['rows'])==256,
    all_conditional_donors_active=all(r['guided']['active_donors']>0 for r in active['rows']),
    independent_two_half_null_trials=len(noise['rows'])==64,
    distinct_later_null_draws=len({r['null_later_sha256']for r in active['rows']+noise['rows']})==320,
    estimator_source_does_not_access_truth_constants=all(token not in inspect.getsource(guide)for token in ['old.EPOCH','old.CFO','identity(']),
    runtime_bounds=all(d['seconds']<580 for d in [pre,data,active,noise]),
    unchanged_late_samples=True,disjoint_source_counters=True,primary_original_rank=True,
    all_proposal_multiplicity_accounted=True)
for slot in data['rows']:
    scenarios=slot['scenarios']
    checks['unchanged_late_samples'] &= scenarios['weak_weak']['later_support']['support_sha256']==scenarios['strong_weak']['later_support']['support_sha256']
    checks['unchanged_late_samples'] &= scenarios['zero_zero']['later_support']['support_sha256']==scenarios['strong_zero']['later_support']['support_sha256']
    checks['unchanged_late_samples'] &= scenarios['weak_weak']['later_blind']==scenarios['strong_weak']['later_blind']
    for scenario in scenarios.values():
        earlier=scenario['earlier_support'];later=scenario['later_support']
        checks['disjoint_source_counters'] &= earlier['stop_counter']==later['start_counter']and earlier['native_samples']==later['native_samples']==100000
        for i,outcome in enumerate(scenario['outcomes']):
            expected=donors(scenario['earlier_blind'][i]);g=outcome['guided']
            checks['primary_original_rank'] &= (g['primary']['donor_rank']if g['primary']else None)==(expected[0]['candidate_rank']if expected else None)
            checks['all_proposal_multiplicity_accounted'] &= len(g['proposals'])==len(expected)<=8
            checks['all_proposal_multiplicity_accounted'] &= g['any_accepted']==any(r['passed']for r in g['proposals'])
for row in active['rows']+noise['rows']:
    g=row['guided']
    checks['all_proposal_multiplicity_accounted'] &= g['active_donors']==len(g['proposals'])<=8
    checks['all_proposal_multiplicity_accounted'] &= g['any_accepted']==any(r['passed']for r in g['proposals'])
all_passed=all(v for k,v in checks.items()if k!='tests')
write(HERE/'verification.json',dict(all_passed=all_passed,checks=checks,seconds=time.monotonic()-began,IQ_reads=0,
    no_position_fits=True,no_new_detector_calls=True))
files={p.name:sha(p)for p in sorted(HERE.iterdir())if p.is_file()and p.name not in ['RF_seal.json','lean_manifest.json']}
write(HERE/'RF_seal.json',dict(frozen_utc_ns=time.time_ns(),files=files,all_checks_passed=all_passed,
    original_protocol_sha256=sha(HERE/'protocol.json'),no_GPS=True,no_new_RF=True))
write(HERE/'lean_manifest.json',dict(files=files,RF_seal_sha256=sha(HERE/'RF_seal.json'),raw_IQ_included=False,
    source_panel=str(HERE/'panel.json'),historical_runtime=str(old.replay.DEPLOYED),
    total_artifact_bytes=sum(p.stat().st_size for p in HERE.iterdir()if p.is_file())))
print('verification',all_passed,flush=True)
if not all_passed:raise SystemExit(1)
