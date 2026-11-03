"""Verify immutable evidence and the frozen gate without rerunning fits."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    checked = {}
    bindings = 0
    roots = [HERE, HERE.parent/'joint_receiver_association',
             HERE.parent/'offline_orbit_pilot', HERE.parent/'offline_orbit_ablation']
    documents = [p for root in roots for p in root.rglob('*.json')]
    for path in documents:
        doc = json.loads(path.read_text())
        if not isinstance(doc, dict):
            continue
        for key in ('sources', 'sources_sha256'):
            sources = doc.get(key, {})
            if not isinstance(sources, dict):
                continue
            for source, expected in sources.items():
                if not isinstance(expected, str):
                    continue
                expected = expected.removeprefix('sha256:')
                if len(expected) != 64 or any(c not in '0123456789abcdef' for c in expected):
                    continue
                # Historical documents also store named digest fields here.
                # File bindings use absolute paths; never ignore a missing file.
                if not Path(source).is_absolute():
                    continue
                if source not in checked:
                    checked[source] = digest(source)
                assert checked[source] == expected, (path, source)
                bindings += 1
    receipts = [json.loads(p.read_text()) for p in sorted(HERE.glob('center-*.receipt.json'))]
    assert len(receipts) == 12 and all(r['exit_code'] == 0 for r in receipts)
    failed = [json.loads(p.read_text()) for p in sorted(HERE.glob('states-*.receipt.json'))]
    assert len(failed) == 12 and all(r['exit_code'] != 0 for r in failed)
    result = subprocess.run([sys.executable, '-m', 'unittest', 'test_model'], cwd=HERE,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    validation = json.loads((HERE/'summary.json').read_text())['validation']
    metrics = validation['metrics']
    reductions = {key: 1 - metrics['fitted'][key]/metrics['zero'][key]
                  for key in ('median_position_km', 'mean_position_km')}
    assert reductions['median_position_km'] >= .05
    assert reductions['mean_position_km'] < .05 and not validation['passed']
    output = dict(passed=True, json_files=len(documents), bindings=bindings,
                  audit_roots=[str(p) for p in roots],
                  broader_legacy_audit_issue={
                      'artifact': str(HERE.parent/'robust/runs/wave1/scale50_00.json'),
                      'source': str(HERE.parent/'robust/model.py'),
                      'issue': 'stored source hash differs from current bytes',
                      'resolved': False},
                  unique_sources=len(checked), new_component_tests_passed=3,
                  test_output=result.stdout+result.stderr, successful_exports=12,
                  preserved_failed_exports=12,
                  maximum_worker_elapsed_s=max(r['elapsed_s'] for r in receipts),
                  reference_proxy_reductions=reductions,
                  forecast_validation_gate_passed=False,
                  causal_position_improvement_established=False, goal_status='active',
                  sources={str(p):digest(p) for p in
                           (Path(__file__), HERE/'test_model.py', HERE/'summary.json')})
    destination=HERE.parent/'joint_receiver_association'/'progress-audit-16.json'
    with destination.open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
