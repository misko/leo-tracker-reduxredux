"""Package only the completed, positive aggregate prior experiment for review."""

import io
import json
import tarfile
import shutil
import importlib.metadata
from pathlib import Path

from run_algo01_ds23_sample import ROOT, read, write, sha
from run_algo02_ds23 import source_closure

SOURCE = ROOT/'reports/2026_10_20_ds23_causal_phase_location_full'
BASELINE = ROOT/'reports/2026_10_19_algo02_ds23_full'
REPORT = ROOT/'reports/2026_10_20_ds23_causal_phase_location_report'


def main():
    evaluation = read(SOURCE/'evaluation.json')
    if not evaluation['positive_generalization_criterion_pass']:
        raise ValueError('publication criterion failed; do not create a positive report')
    protocol = read(SOURCE/'protocol.json')
    for name,digest in protocol['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('frozen new inference source changed: '+name)
    REPORT.mkdir(parents=True, exist_ok=True)
    mapping = {name:name for name in ('protocol.json','execution.json','evaluation.json','evaluation_audit.json',
                                    'positions.csv','frequency_fit_summary.json')}
    mapping.update({name:'figures/'+name for name in ('position_error_distribution.png','paired_position_errors.png','position_error_changes.png')})
    for source,target in mapping.items():
        destination = REPORT/target;destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.suffix == '.csv':
            destination.write_text((SOURCE/source).read_text())
        else:
            shutil.copyfile(SOURCE/source,destination)
    for directory,name in (('2026_10_20_ds23_causal_phase_location','development40'),
                           ('2026_10_20_ds23_causal_phase_location_validation','prior_validation20')):
        destination = REPORT/'evidence'/name;destination.mkdir(parents=True,exist_ok=True)
        for file in ('protocol.json','execution.json'):
            shutil.copyfile(ROOT/'reports'/directory/file,destination/file)
    diagnostic = ROOT/'reports/2026_10_20_ds23_0041_influence'
    for file in ('family_receiver_ablation.png','regional_multistart.png'):
        shutil.copyfile(diagnostic/file,REPORT/'figures'/('scan41_'+file))
    shutil.copyfile(diagnostic/'evaluation.json',REPORT/'evidence/scan41_influence_evaluation.json')
    roots = [Path('tools')/(name+'.py') for name in (
        'ds23_causal_phase_location','probe_ds23_causal_phase_location','validate_ds23_causal_phase_location',
        'run_ds23_causal_phase_location_full','evaluate_ds23_causal_phase_location_full',
        'debug_ds23_0041_influence','probe_ds23_0041_curve_reentry','debug_ds23_0041_multistart','plot_ds23_0041_influence')]
    roots.extend([Path('tests/analysis/test_ds23_causal_phase_location.py'),
                  Path('tests/analysis/test_ds23_causal_phase_location_reporting.py')])
    closure = source_closure(roots)
    for name,digest in closure.items():
        destination = REPORT/'source_snapshot'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,destination)
        if sha(destination) != digest:
            raise ValueError('snapshot copy changed')
    write(REPORT/'source_snapshot/sha256.json',closure)
    inventory = {}
    evidence = read(SOURCE/'evaluation_audit.json')['evidence']
    with tarfile.open(REPORT/'numerical_evidence.tar.xz','w:xz',preset=6) as archive:
        for case,record in evidence.items():
            path = ROOT/record['path']
            document = read(path)
            if sha(path) != record['sha256']:
                raise ValueError('trial changed after evaluation')
            compact = {k:v for k,v in document.items() if k not in ('baseline_arms','policy_arms')}
            if not compact['selection']['qualified']:
                compact.pop('arms')
            compact['source_trial_sha256'] = record['sha256']
            compact['original_ALGO02_sha256'] = sha(BASELINE/case/'algo02_result.json')
            encoded = json.dumps(compact,separators=(',',':'),allow_nan=False).encode()
            member = tarfile.TarInfo(case+'.json');member.size=len(encoded);member.mtime=0
            archive.addfile(member,io.BytesIO(encoded))
            inventory[case] = dict(source=record['path'], source_sha256=record['sha256'], compact_bytes=len(encoded))
    write(REPORT/'numerical_evidence_inventory.json',dict(cases=inventory,
        values_preserved_losslessly_except_redundant_baseline_and_policy_copies=True,
        unqualified_arms_equal_original_ALGO02_policy=True,
        reconstruction='baseline_arms from original ALGO02; policy_arms = trial arms iff paired_valid, otherwise original baseline; unqualified arms equal baseline',
        archive_sha256=sha(REPORT/'numerical_evidence.tar.xz')))
    write(REPORT/'runtime_versions.json',{name:importlib.metadata.version(name) for name in ('numpy','scipy','matplotlib','sgp4','pytest')})
    files = [p for p in REPORT.rglob('*') if p.is_file() and p.name!='publication_manifest.json']
    write(REPORT/'publication_manifest.json',{str(p.relative_to(REPORT)):dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(files)})
    print('Packaged',len(evidence),'trials and',len(closure),'source files;',
          'archive MB',round((REPORT/'numerical_evidence.tar.xz').stat().st_size/1e6,2),flush=True)


if __name__=='__main__':
    main()
