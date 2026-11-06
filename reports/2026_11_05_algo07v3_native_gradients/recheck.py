"""Recheck saved native outputs after correcting explicit empty source declarations."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from compare_algo07v3_runs import compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    bindings = json.loads((root / 'plan.json').read_bytes())['bindings']
    checker = Path('tools/compare_algo07v3_runs.py').resolve()
    original = Path(__file__).with_name('measured') / 'compare_algo07v3_runs.py'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == bindings[str(checker)]
    expected = original.read_text().replace(
        'def module_changes(a, b, expected_changed, expected_added):\n',
        'def module_changes(a, b, expected_changed, expected_added):\n'
        '    if expected_changed is None:\n'
        '        expected_changed = ["leo.analysis.localization_v3.hierarchical"]\n', 1).replace(
            'args.changed_module or ["leo.analysis.localization_v3.hierarchical"],',
            'args.changed_module,', 1)
    assert checker.read_text() == expected
    for name, sha in bindings.items():
        source = original if name == str(checker) else Path(name)
        assert hashlib.sha256(source.read_bytes()).hexdigest() == sha, name
    value = compare(SimpleNamespace(
        baseline_request=root / 'baseline/request.json',
        candidate_request=root / 'candidate/request.json',
        baseline_timing=root / 'baseline/supervisor.json',
        candidate_timing=root / 'candidate/supervisor.json', changed_module=[], added_module=[]))
    value.update(external_function_substitution=True,
                 validator_only_correction=dict(
                     original_sha256=bindings[str(checker)],
                     corrected_sha256=hashlib.sha256(checker.read_bytes()).hexdigest(),
                     archived_original=str(original.resolve()),
                     exact_source_patch_verified=True),
                 probe_sha256=bindings[str(Path('tools/probe_algo07v3_native_gradients.py').resolve())])
    with (root / 'comparison.json').open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: value[k] for k in ('exact_owned_science_and_artifacts',
                                           'source_changes', 'observed_process_seconds')}))


if __name__ == '__main__':
    main()
