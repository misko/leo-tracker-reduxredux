"""Package exact research artifacts without duplicating large derived TLE arrays."""

import gzip
import shutil
import tarfile
from pathlib import Path
from run_algo01_ds23_sample import ROOT,read,write,sha
from probe_ds23_history_calibrated_phase import HISTORY

STUDY=ROOT/'reports/2026_10_19_ds23_curvature_shape_study'
ASSOCIATION=ROOT/'reports/2026_10_19_ds23_association_evidence'
GROUPS={STUDY:['ds23_fragment_covariance','ds23_causal_shape_ensemble','ds23_statistical_curvature',
               'ds23_curvature_shape_combination','dynamic_pilot_timing'],
        ASSOCIATION:['ds23_fixed_confidence','ds23_joint_family_search','ds23_secondary_curves']}
TOOLS=['probe_ds23_fragment_covariance.py','run_ds23_fragment_covariance.py',
       'learn_ds23_causal_shape_forecast.py','learn_ds23_causal_shape_ensemble.py',
       'probe_ds23_causal_shape_ensemble.py','run_ds23_causal_shape_ensemble.py',
       'probe_ds23_statistical_curvature.py','run_ds23_statistical_curvature.py',
       'probe_ds23_curvature_shape_combination.py','run_ds23_curvature_shape_combination.py',
       'probe_dynamic_pilot_timing.py','probe_ds23_fixed_confidence.py','run_ds23_fixed_confidence.py',
       'probe_ds23_joint_family_search.py','probe_ds23_secondary_curves.py','run_ds23_association_diagnostics.py',
       'complete_ds23_association_diagnostics.py','resume_ds23_large_joint_search.py',
       'audit_ds23_satellite_correction_transfer.py','report_ds23_association_evidence.py',
       'report_ds23_curvature_shape_study.py','package_ds23_evidence_studies.py']
TESTS=['test_ds23_fragment_covariance_tool.py','test_ds23_causal_shape_forecast_tool.py',
       'test_ds23_causal_shape_ensemble_tool.py','test_dynamic_pilot_timing_tool.py',
       'test_ds23_statistical_curvature_tool.py','test_ds23_fixed_confidence_tool.py',
       'test_ds23_joint_family_search_tool.py','test_ds23_secondary_curves_tool.py','test_ds23_joint_checkpoint_tool.py']


def archive(destination,files):
    inventory=[]
    with (destination/'evidence.tar.gz').open('wb') as raw:
        with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed,mode='w') as output:
                for path in sorted(files):
                    relative=str(path.relative_to(ROOT));before=sha(path)
                    inventory.append(dict(path=relative,sha256=before,bytes=path.stat().st_size))
                    info=output.gettarinfo(str(path),arcname=relative);info.mtime=0;info.uid=info.gid=0;info.uname=info.gname=''
                    with path.open('rb') as stream:output.addfile(info,stream)
                    assert before==sha(path),'artifact changed while packaging'
    # Re-read every archived member, independently checking content hashes.
    import hashlib
    with tarfile.open(destination/'evidence.tar.gz','r:gz') as output:
        for member,entry in zip(output.getmembers(),inventory,strict=True):
            assert member.name==entry['path'] and member.size==entry['bytes']
            assert hashlib.sha256(output.extractfile(member).read()).hexdigest()==entry['sha256']
    write(destination/'evidence_inventory.json',dict(archive='evidence.tar.gz',sha256=sha(destination/'evidence.tar.gz'),
        members=inventory,all_archive_members_verified=True,unpack_at_repository_root=True,
        compression_is_lossless_no_scientific_values_rewritten=True))


def run():
    cases=read(ROOT/'reports/2026_10_19_ds23_fragment_covariance/protocol.json')['cases']
    history_receipts=STUDY/'history_receipts';history_receipts.mkdir(exist_ok=True)
    for case in cases:
        path=HISTORY/(case+'_shape_forecast.json');full=read(path)
        receipt={k:v for k,v in full.items() if k!='transitions'}
        receipt.update(full_derived_file_sha256=sha(path),full_derived_file_bytes=path.stat().st_size,
            transition_count=len(full['transitions']),this_is_a_compact_receipt_not_the_hashed_transition_input=True,
            omitted_arrays_rebuild_command=f'PYTHONPATH=src:tools .venv/bin/python tools/learn_ds23_causal_shape_forecast.py {path.relative_to(ROOT).with_name(case+".json")}',
            full_derived_file_name=path.name)
        write(history_receipts/(case+'_shape_forecast_receipt.json'),receipt)
        shutil.copyfile(HISTORY/(case+'_shape_ensemble.json'),history_receipts/(case+'_shape_ensemble.json'))
    for destination,names in GROUPS.items():
        files=[]
        for name in names:
            directory=ROOT/'reports'/('2026_10_19_'+name)
            files.extend(p for p in directory.rglob('*') if p.is_file() and p.suffix in ('.json','.log','.py'))
        archive(destination,files)
        snapshot=destination/'source_snapshot'
        for name in TOOLS:
            target=snapshot/'tools'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/'tools'/name,target)
        for name in TESTS:
            source=ROOT/'tests/analysis'/name
            if source.exists():
                target=snapshot/'tests/analysis'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        (snapshot/'README.md').write_text('Research reproduction overlay on previously published ALGO01/DBG01 source snapshots.\n'
            'Unpack evidence.tar.gz at repository root to restore exact original report paths.\n'
            'Input GLRT/TLE authorities and baseline tools retain their published hashes.\n'
            'The history_receipts directory contains compact receipts, not replacement transition inputs.\n'
            'Regenerate large shape transition arrays using their recorded commands before replaying hashes.\n')
        write(destination/'source_inventory.json',{str(p.relative_to(snapshot)):sha(p) for p in sorted(snapshot.rglob('*')) if p.is_file()})
        print(destination.name,'archive MB',round((destination/'evidence.tar.gz').stat().st_size/1e6,2),flush=True)


if __name__=='__main__':run()
