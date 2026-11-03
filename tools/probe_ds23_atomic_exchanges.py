"""Test every mutually preferred exchange already nominated across full DS23."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import signal
import time
import numpy as np

from run_algo01_ds23_sample import ROOT,read,write,sha
from probe_ds23_family_cavity_nominations import setup
from probe_ds23_family_cavity_position import trial
from audit_ds23_family_cavity import position as audit_position

SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23'
INVENTORY=ROOT/'reports/2026_10_22_ds23_position_cavity/atomic_exchange_inventory.json'
OUT=ROOT/'reports/2026_10_22_ds23_atomic_exchanges'


def initialize():
    path=OUT/'protocol.json'
    if path.exists():return read(path)
    inventory=read(INVENTORY);authority=read(SOURCE/'position/independent_numerical_audit.json')
    if (not authority['all_passed'] or authority['source_execution_sha256']!=inventory['source_execution_sha256']
            or sha(SOURCE/'position/execution.json')!=inventory['source_execution_sha256']):
        raise ValueError('atomic offers differ from audited full-population source')
    receipts={n['case']:dict(nomination_sha256=n['source_sha256'],position_sha256=next(p['source_sha256'] for p in authority['positions'] if p['case']==n['case'])) for n in authority['nominations']}
    protocol=dict(cases=[r['case'] for r in inventory['rows']],source_rows=inventory['rows'],
        source_receipts={r['case']:receipts[r['case']] for r in inventory['rows']},
        population=410,dataset_total=413,unchanged_cases=410-len(inventory['rows']),
        selection_reads_only_positive_RF_nominations_not_GPS_errors=True,
        every_mutual_pair_among_existing_top4_offers_tested=True,
        both_replacements_apply_to_original_labels_atomically=True,
        original_whole_family_trials_and_signed_fallback_remain_candidates=True,
        primary_adoption='minimum corrected normalized c0 evidence; paired original gates and phase convergence; positive gain over previous selected model',
        same_latent_coordinate_count_and_prior_hyperparameters=True,
        physical_mode_ownership_rule_unchanged_but_support_follows_swapped_families=True,
        all_original_points_and_other_labels_aliases_preserved=True,
        cold_start=[0,0],regional_width_km=25,phase_rounds=5,position_steps=48,
        matched_c0_fitted_c_observations_candidates_priors_and_budgets=True,
        no_GPS_RF_future_TLE_or_point_deletion=True,per_case_seconds=360,
        source_execution_sha256=inventory['source_execution_sha256'],inventory_sha256=sha(INVENTORY),
        source_tools_sha256={p.name:sha(p) for p in [Path(__file__),ROOT/'tools/probe_ds23_family_cavity_position.py']})
    OUT.mkdir(parents=True,exist_ok=True);write(path,protocol);return protocol


def run(case):
    path=OUT/(case+'.json')
    if path.exists():return read(path)
    began=time.monotonic();signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('360s atomic exchange case cap')));signal.alarm(360)
    try:
        protocol=read(OUT/'protocol.json');row=next(r for r in protocol['source_rows'] if r['case']==case);receipt=protocol['source_receipts'][case]
        npth=SOURCE/(case+'_nominations.json');ppth=SOURCE/'position'/(case+'.json')
        assert sha(npth)==receipt['nomination_sha256'] and sha(ppth)==receipt['position_sha256']
        nomination=read(npth);families={f['original_norad']:f for f in nomination['families']};d=setup(case);trials=[]
        for pair in row['dependent_pairs_skipped_by_current_configuration_rule']:
            if not pair['mutual_swap']:raise ValueError('inventory contains an unplanned dependent chain')
            offers=[]
            for original,new in [pair['first'],pair['second']]:
                f=families[original];o=f['best'];assert o['norad']==new and f['predictive_gain']>0
                offers.append((f,o))
            r=trial(d,offers)
            np.testing.assert_allclose(r['means'],d['means'],rtol=0,atol=1e-12)
            width=d['base'].hardware.shape[1]+d['base'].smooth.shape[1]+len(d['base'].labels)+3*len(d['base'].supported)+len(d['base'].members)
            for arm,value in r['arms'].items():assert len(value['coefficient'])==width+int(arm=='fitted_c')
            trials.append(r);print(case,'atomic exchange',r['replacements'],'paired gates',r['paired_valid'],flush=True)
        previous=read(ppth)
        result=dict(case=case,status='complete',trials=trials,source_previous_position_sha256=receipt['position_sha256'],
            source_nomination_sha256=receipt['nomination_sha256'],baseline_corrected_loss=previous['baseline_corrected_loss'],
            original_mask=d['keep'],powers=d['powers'],model=d['model'],baseline_node=d['node'],baseline_entries=d['entries'],baseline_means=d['means'],
            all_original_points_preserved=True,reference_position_used=False,seconds=time.monotonic()-began)
    except Exception as exc:
        import traceback
        traceback.print_exc();result=dict(case=case,status='failed',error=repr(exc),seconds=time.monotonic()-began)
    finally:signal.alarm(0)
    write(path,result);return result


def audit(case):
    saved=read(OUT/(case+'.json'));protocol=read(OUT/'protocol.json');receipt=protocol['source_receipts'][case]
    assert saved['status']=='complete'
    original=read(SOURCE/'position'/(case+'.json'));nomination=read(SOURCE/(case+'_nominations.json'))
    assert sha(SOURCE/'position'/(case+'.json'))==receipt['position_sha256']
    assert sha(SOURCE/(case+'_nominations.json'))==receipt['nomination_sha256']
    families={f['original_index']:f for f in nomination['families']};mapping_checks=[]
    for t in saved['trials']:
        changes={r['original_index']:r['candidate_index'] for r in t['replacements']}
        assert len(changes)==2 and set(changes)==set(changes.values())
        alias={m['component']:int(a) for old in changes for m,a in zip(families[old]['members'],families[old]['best']['aliases'],strict=True)}
        for k,(old,new) in enumerate(zip(original['baseline_node']['seed']['rows'],t['node']['seed']['rows'],strict=True)):
            assert new['component']==old['component'] and new['candidate_index']==changes.get(old['candidate_index'],old['candidate_index'])
            expected=alias[old['component']] if old['candidate_index'] in changes and old['component'] in alias else original['baseline_node']['aliases'][k]
            assert t['node']['aliases'][k]==expected
        for old,new in zip(original['baseline_entries'],t['entries'],strict=True):
            assert old['observation_ids']==new['observation_ids'] and old['points']==new['points']
            assert new['candidate_index']==changes.get(old['candidate_index'],old['candidate_index'])
            assert new['alias']==(alias[old['component']] if old['candidate_index'] in changes else old['alias'])
        np.testing.assert_array_equal(original['original_mask'],saved['original_mask'])
        np.testing.assert_array_equal(original['powers'],saved['powers'])
        assert original['model']==saved['model']
        mapping_checks.append(dict(mutual_bijection=True,all_original_curved_and_predictive_rows_preserved=True))
    numerical=audit_position(case,position_dir=OUT)
    return dict(case=case,mapping_checks=mapping_checks,numerical=numerical,all_passed=True,
        current_and_previous_causal_nomination_authority_checked=True,reference_position_used=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['fit','audit'],required=True);parser.add_argument('--workers',type=int,default=6)
    args=parser.parse_args();protocol=initialize()
    if not 1<=args.workers<=30:raise ValueError('1to30workers required')
    rows=[];function=run if args.stage=='fit' else audit
    if args.stage=='audit' and not read(OUT/'execution.json')['all_terminal']:raise ValueError('fit stage not terminal')
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for f in as_completed([pool.submit(function,c) for c in protocol['cases']]):
            rows.append(f.result());write(OUT/(args.stage+'_progress.json'),dict(rows=rows,completed=len(rows),total=len(protocol['cases'])))
    name='execution.json' if args.stage=='fit' else 'independent_numerical_audit.json'
    write(OUT/name,dict(rows=rows,all_terminal=True,all_passed=all(r.get('all_passed',False) for r in rows) if args.stage=='audit' else None,
        no_geographic_evaluation_yet=True))


if __name__=='__main__':main()
