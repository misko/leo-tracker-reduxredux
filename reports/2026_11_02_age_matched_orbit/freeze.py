"""Seal the new age-prior experiment after implementation and preflight review."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OLD=ROOT.parent/'2026_11_02_generalized_corrections'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output=ROOT/'protocol.json'
    if output.exists() or (ROOT/'evaluation/execution_started.json').exists():
        raise FileExistsError('Single prospective seal and execution only')
    config=json.loads((ROOT/'evaluation/proposed_configuration.json').read_text())
    preflight=json.loads((ROOT/'evaluation/preflight.json').read_text())
    assert preflight['status']=='passed' and preflight['no_position_optimization']
    previous=json.loads((OLD/'execution_protocol.json').read_text())
    sources={Path(p) for p in previous['source_sha256']}
    for path,expected in previous['source_sha256'].items():
        assert sha(path)==expected,('Previous frozen source changed',path)
    runtime=preflight['runtime_repo_source_sha256']
    assert runtime, 'Runtime dependency inventory required'
    for path,expected in runtime.items():
        assert sha(path)==expected,('Preflight runtime source changed',path)
        sources.add(Path(path))
    for folder in ['evaluation','review']:
        sources.update((ROOT/folder).glob('*.py'))
    sources.update([ROOT/'covariance/age_covariance.py',ROOT/'covariance/test_age_covariance.py',ROOT/'freeze.py'])
    spec=importlib.util.spec_from_file_location('freeze_age_covariance',ROOT/'covariance/age_covariance.py')
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    inventory=ROOT/'covariance/derived_inventory.json'
    protocol=dict(created_utc_ns=time.time_ns(),revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        evaluation=config,covariance_policy=model.POLICY,
        previous_combined_results_sha256=sha(OLD/'evaluation/combined_results.json'),
        previous_independent_audit_sha256=sha(OLD/'review/combined_audit.json'),
        support_inventory_sha256=sha(inventory),design_sha256=sha(ROOT/'DESIGN.md'),
        preflight_sha256=sha(ROOT/'evaluation/preflight.json'),
        source_sha256={str(p):sha(p) for p in sorted(sources)},
        validation='Fixed .5 shrinkage, no fitted hyperparameters; historical snapshot connectivity prevents independent archive holdout validation',
        policies={'Age3':'primary >=3 nonreused historical forecast pairs; paired numerical/physical/native qualification',
                  'Age2':'exploratory >=2 pairs; identical covariance/endpoints and all other gates'},
        fallback='exact immutable selected A; previous ALGO07/B outcomes are comparators only',
        nomination='previous saved generic RF nomination, no reranking or old-attempt retry',
        selection='no new covariance selection by RF score, geographic error or scan-specific exception',
        coverage_policy_decision='two-pair exploratory tier added prospectively after metadata-only support inventory, before new RF outcomes',
        execution='one8worker1200s run,120s cells,no retry/completion extension,full205 terminal ledger',
        geography='postdecision evaluation only after RF ledger seal and independent audit',
        scope='same-site retrospective development, fixed observations/associations and matched c arms')
    output.write_text(json.dumps(protocol,indent=2)+'\n')
    print(json.dumps(dict(protocol_sha256=sha(output),sources=len(sources),candidate_cases=len(config['candidate_cases'])),indent=2))


if __name__=='__main__':main()
