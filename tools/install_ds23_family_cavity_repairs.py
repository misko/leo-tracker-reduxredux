"""Install verified terminal edge repairs, retaining every original failed file."""

from pathlib import Path
import shutil

from run_algo01_ds23_sample import ROOT,read,write,sha
from stage_ds23_family_cavity_outputs import SOURCE,TARGET


def install(original,repaired,archive):
    if not repaired.exists() or read(repaired)['status']!='complete':raise ValueError('repair is not a completed result')
    if original.is_symlink() and original.resolve()==repaired.resolve():return None
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():shutil.copy2(original,archive)
    if sha(original)!=sha(archive):raise ValueError('original failed result archive does not match')
    before=sha(original);original.unlink();original.symlink_to(repaired)
    return dict(path=str(original.relative_to(ROOT)),original_sha256=before,original_archive=str(archive),
        repaired_path=str(repaired),repaired_sha256=sha(repaired))


def main():
    assert read(SOURCE/'nomination_stage.json')['all_terminal'] and read(SOURCE/'position_stage.json')['all_terminal']
    empty=TARGET/'empty_history_repair';legacy=TARGET/'legacy_reference_repair'
    assert read(empty/'execution.json')['all_terminal'] and read(legacy/'execution.json')['all_terminal']
    changes=[]
    for case in ['DS23-0130','DS23-0260']:
        for relative,repair in [(Path(case+'_nominations.json'),empty/(case+'_nominations.json')),
                (Path('position')/(case+'.json'),empty/'position'/(case+'.json'))]:
            change=install(SOURCE/relative,repair,TARGET/'original_failed_results'/relative)
            if change:changes.append(change)
    for case in ['DS23-0074','DS23-0365']:
        relative=Path('position')/(case+'.json');change=install(SOURCE/relative,legacy/(case+'.json'),TARGET/'original_failed_results'/relative)
        if change:changes.append(change)
    protocol=read(SOURCE/'protocol.json');cases=protocol['cases'];rows=[read(SOURCE/'position'/(c+'.json')) for c in cases]
    receipt=dict(changes=changes,case_count=len(rows),all_terminal=True,
        nomination_complete=sum(read(SOURCE/(c+'_nominations.json'))['status']=='complete' for c in cases),
        position_complete=sum(r['status']=='complete' for r in rows),
        original_stage_receipts_preserved_separately=True,no_GPS_candidate_or_prior_hyperparameter_tuning=True,
        missing_history_uses_existing_radial0p5km_cross0p25km_fallback=True,
        legacy_reference_replayed_from_saved_history_without_new_position_optimization=True,
        null_loss_tolerance_and_residual_gates_unchanged=True,
        source_sha256={name:sha(ROOT/'tools'/name) for name in ['prototype_s01_causal_shape.py','ds23_family_cavity.py','probe_ds23_family_cavity_position.py']})
    write(SOURCE/'edge_repair_manifest.json',receipt)
    execution=SOURCE/'position/execution.json';archive=TARGET/'original_failed_results/position_execution_before_repairs.json'
    if not archive.exists():shutil.copy2(execution,archive)
    corrected=TARGET/'position_execution_after_repairs.json'
    write(corrected,dict(rows=rows,all_terminal=True,no_geographic_error_evaluation_yet=True,
        repair_manifest_sha256=sha(SOURCE/'edge_repair_manifest.json')))
    execution.unlink();execution.symlink_to(corrected)
    print(dict(cases=len(rows),nominations_complete=receipt['nomination_complete'],positions_complete=receipt['position_complete'],installed_files=len(changes)),flush=True)


if __name__=='__main__':main()
