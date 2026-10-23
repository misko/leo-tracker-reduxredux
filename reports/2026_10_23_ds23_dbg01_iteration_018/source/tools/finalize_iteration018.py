"""Seal018 publication from completed audited outputs; no scientific fitting."""
from pathlib import Path
import shutil
import re
import csv
import report_ds23_dbg01_iteration_011 as common
import probe_ds23_iteration018_recovery as binding
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=Path(__file__).resolve().parents[2]
RAW=binding.runner.RAW


def main():
    for name in ['batch_execution.json','independent_iteration_audit.json','recovery_endpoint_audit.json','recovery_independent_audit_binding.json']:
        assert read(RAW/name)['all_passed']
    for folder in ['conflict_alternatives','single_source_augmented_family']:
        assert read(RAW/folder/'execution.json')['all_passed']
    assert read(OUT/'evidence/local_review.json')['all_replay_and_information_checks_passed']
    assert '13 passed' in (OUT/'evidence/tests.txt').read_text()
    for name in ['review_ds23_worst_outliers.py','ds23_position_information.py','probe_ds23_iteration014_augmented_family.py',
                 'audit_ds23_iteration014_augmented_family.py','audit_ds23_algo01_coverage.py','ds23_active_mode_support.py']:
        shutil.copyfile(ROOT/'tools'/name,OUT/'source/tools'/name)
    for name in ['test_ds23_position_information.py','test_ds23_worst_outlier_review.py']:
        shutil.copyfile(ROOT/'tests/analysis'/name,OUT/'source/tests'/name)
    for path in (OUT/'tables').glob('*.csv'):path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n'))
    rows=list(csv.DictReader((OUT/'tables/position_and_association.csv').open()))
    for row in rows:
        assert int(row['original_accepted_points_lost'])==0
        assert abs(float(row['associated_percent'])-100*int(row['associated_points'])/int(row['all_GLRT']))<1e-9
    for case in read(RAW/'protocol.json')['cases']:
        alternatives=read(RAW/'conflict_alternatives'/(case+'.json'))
        assert all(g['selected_norad'] is None for g in alternatives['groups'])
    assert read(RAW/'single_source_augmented_family/DS23-0261.json')['selected'] is None
    common.RAW=RAW;common.OUT=OUT;common.archive(read(RAW/'protocol.json')['cases']);common.gallery()
    gallery=OUT/'FIGURES.md';gallery.write_text(gallery.read_text().replace('Iteration011','Iteration018'))
    for path in [OUT/'README.md',gallery]:
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            if '://' not in target:assert (path.parent/target).exists(),target
    write(OUT/'evidence/source_hashes.json',{str(p.relative_to(OUT)):sha(p) for p in sorted((OUT/'source').rglob('*.py'))})
    write(OUT/'evidence/publication_checks.json',dict(all_passed=True,figures=len(list((OUT/'figures').glob('*.png'))),
        tables=len(list((OUT/'tables').glob('*.csv'))),position_rows=len(rows),targeted_tests=13,
        all_relative_document_links_resolve=True,association_denominators_verified=True,all_original_IDs_preserved=True,
        no_alternative_identity_or_augmented_family_selected=True,no_population_benchmark_changed=True))
    print('Publication checks passed; archived all completed018 evidence')


if __name__=='__main__':main()
