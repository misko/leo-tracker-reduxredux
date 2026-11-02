"""Freeze prototype policies and scientific sources before population fits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    destination = ROOT / 'protocol.json'
    if destination.exists() or (ROOT/'evaluation/execution_started.json').exists():
        raise FileExistsError('Protocol or execution already exists')
    configuration = json.loads((ROOT/'evaluation/proposed_configuration.json').read_text())
    roster = Path(configuration['roster_path'])
    assert sha(roster) == configuration['roster_sha256']
    previous = json.loads((REPO/'reports/2026_11_02_predictive_reliability/protocol.json').read_text())
    dependencies = {Path(p) for p in previous['source_sha256'] if '/tools/' in p or '/src/' in p}
    dependencies.update((REPO/'tools/algo07_science').glob('*.py'))
    dependencies.update((REPO/'tools/algo06_science').glob('*.py'))
    dependencies.update(ROOT.rglob('*.py'))
    covariance = module('frozen_generalized_covariance', ROOT/'covariance/causal_covariance.py')
    guard = module('frozen_generalized_guard', ROOT/'identifiability/guard.py')
    protocol = dict(created_utc_ns=time.time_ns(),
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        evaluation=configuration, covariance_policy=covariance.POLICY,
        identifiability_policy=guard.POLICY,
        model_names={'ALGO07':'exact saved comparator',
                     'A':'numerically triggered half damping plus central-derivative rescue',
                     'A+B':'A plus independently constructed causal-history orbital covariance',
                     'A+B+C':'same B endpoints with other-family displacement-support guard'},
        selection=dict(A='both-arm numerical/physical/native qualification and position nondegradation under a common final reference; otherwise saved ALGO07',
            B='generic first RF-nominated family; covariance chosen only from causal orbital history; both-arm qualification; otherwise selected A',
            C='B accepted plus frozen other-family projection guard in BOTH c arms; otherwise selected A',
            normalized_RF_gains='diagnostic only for covariance selection; no GPS selection',
            existing_guarded_ALGO07_replacements='preserved exactly',
            missing_or_inconsistent_evidence='explicit unchanged fallback'),
        observations='fixed native graph, identities, aliases, priors except nominated covariance, empirical weights and full ownership union; no GLRT recovery',
        starts='same saved RF fitted-c endpoint and reference for both arms/models; operational 25x25km box unchanged',
        causal_history='epoch and archived availability <= scan cutoff; no later-TLE substitution; repeated identical snapshots count once',
        covariance_scope='correlated TLE-disagreement proxy, not calibrated independent orbital truth; three existing modes, zero mean, no new columns',
        identifiability_scope='conservative curved-only in-sample diagnostic, recalibrating shared nuisance and excluding target; no calibrated statistical significance or identity proof',
        geography='root reads previously published error labels only for postdecision evaluation; no site in inference policy',
        generalization='same-site retrospective development comparison; no independent new-location validation',
        execution='one attempt, eight BLAS-one workers,1200s total including per-case loading,120s per model-arm,all workers joined; no retry/budget extension',
        source_sha256={str(p):sha(p) for p in sorted(dependencies)},
        roster_sha256=sha(roster))
    destination.write_text(json.dumps(protocol,indent=2)+'\n')
    print('Frozen protocol', sha(destination), 'with',len(dependencies),'scientific sources')


if __name__ == '__main__':
    main()
