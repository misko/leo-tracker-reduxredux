"""Resume iteration009 with a verified whole-track nomination input contract.

Failed v1 artifacts remain untouched. Reuse0311 only after proving that the
guard leaves its original target list unchanged. Later stages use v2 outputs.
"""

import argparse
from pathlib import Path
import shutil
import sys

import run_ds23_dbg01_iteration_009 as runner
from run_algo01_ds23_sample import read,write,sha

engine=runner.engine
ORIGINAL_CONFIGURE=engine.configure
ORIGINAL_NOMINATE=engine.reentry.nominate
OUT=runner.RAW/'single_curve_reentry_v2'


def whole_targets(inventory,active_components):
    ranking=[r for r in inventory['ranking'] if r['points']==r['original_points'] and r['component'] not in active_components]
    return dict(inventory,ranking=ranking)


def guarded_nomination(data,inventory):
    active={r['component'] for r,sl in zip(data['base'].rows,data['base'].slices,strict=True) if data['keep'][sl].any()}
    filtered=whole_targets(inventory,active)
    result=ORIGINAL_NOMINATE(data,filtered)
    result['whole_target_input_guard']=dict(source_sha256=sha(Path(__file__)),
        excluded_partial_components=[r['component'] for r in inventory['ranking'] if r['points']!=r['original_points']],
        active_calibration_components_excluded=sorted(active),partial_observations_retained_in_inventory=True)
    return result


def configure():
    engine.RAW=runner.RAW;ORIGINAL_CONFIGURE()
    engine.reentry.OUT=OUT;engine.reentry.nominate=guarded_nomination
    engine.support.NOMINATIONS=OUT;engine.finalize.OLD=OUT;engine.audit.REENTRY=OUT


def prepare():
    configure();OUT.mkdir(exist_ok=True);old=runner.RAW/'single_curve_reentry'
    if (OUT/'repair_protocol.json').exists():raise FileExistsError('preserve repaired target experiment')
    write(OUT/'repair_protocol.json',dict(source_sha256=sha(Path(__file__)),old_protocol_sha256=sha(old/'protocol.json'),
        old_nominations_execution_sha256=sha(old/'nominations_execution.json'),old_positions_execution_sha256=sha(old/'positions_execution.json'),
        guard='wholly unassociated original track and no active calibration observation in its source component',
        no_partial_point_or_track_removed_from_original_data_or_DBG01=True,
        no_causal_catalogue_or_priors_gates_budget_change=True,
        failed_v1_nominations_and_positions_preserved=True,only_failed0028_recomputed=True))
    shutil.copyfile(old/'protocol.json',OUT/'protocol.json')
    case='DS23-0311';data=engine.current_setup(case);inventory=read(runner.RAW/case/'inventory.json')['arms']['c0']
    active={r['component'] for r,sl in zip(data['base'].rows,data['base'].slices,strict=True) if data['keep'][sl].any()}
    filtered=whole_targets(inventory,active)
    expected=[r['component'] for r in filtered['ranking'] if r['curved'] and r['points']>=12][:3]
    actual=[r['target']['component'] for r in read(old/(case+'_nominations.json'))['targets']]
    if expected!=actual:raise ValueError('cannot reuse0311 because whole-target guard changes its proposals')
    for suffix in ['nominations','positions']:shutil.copyfile(old/(case+'_'+suffix+'.json'),OUT/(case+'_'+suffix+'.json'))
    write(OUT/'reuse0311_receipt.json',dict(case=case,eligible_target_components=expected,
        source_result_sha256=sha(old/(case+'_positions.json')),reused_result_sha256=sha(OUT/(case+'_positions.json')),
        exact_previous_results_reused_without_refit=True))
    for stage in ['nominations','positions']:
        receipt=engine.reentry.one('DS23-0028',stage)
        rows=[receipt,dict(case='DS23-0311',status='complete',reused=True)]
        write(OUT/(stage+'_execution.json'),dict(rows=rows,all_terminal=True,all_passed=all(r['status']=='complete' for r in rows)))
        if receipt['status']!='complete':raise RuntimeError('repaired '+stage+' failed; stop dependent stages')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',required=True)
    args=parser.parse_args()
    if args.stage=='prepare':prepare();return
    engine.configure=configure;engine.protocol=runner.protocol
    sys.argv=[sys.argv[0],'--stage',args.stage];engine.main()


if __name__=='__main__':main()
