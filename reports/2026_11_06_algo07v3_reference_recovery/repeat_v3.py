"""One fresh v3 run after the original reference; retain the earlier observation."""

import argparse
import json
from pathlib import Path

from run import digest, execute, read, write


def main(parent):
    previous, comparison = read(parent / 'plan.json'), read(parent / 'comparison.json')
    assert comparison['all_checked_values_exact'] and not comparison['missing_audit_mappings']
    for name, sha in previous['bindings'].items():
        assert digest(name) == sha, name
    root = parent / 'after-reference'
    root.mkdir(exist_ok=False)
    request = read(parent / 'v3-request.json')
    request['output_root'] = str(root / 'publication')
    write(root / 'request.json', request)
    (root / 'cli').mkdir()
    command = list(previous['commands']['candidate'])
    replacements = {str(parent / 'candidate-process-time.txt'): str(root / 'process-time.txt'),
                    str(parent / 'v3-run'): str(root / 'cli'),
                    str(parent / 'v3-request.json'): str(root / 'request.json')}
    command = [replacements.get(a, a) for a in command]
    compare = list(previous['commands']['comparison'])
    for flag, value in (('--request', root / 'request.json'),
                        ('--candidate-timing', root / 'cli/attempt/supervisor.json'),
                        ('--output', root / 'comparison.json')):
        compare[compare.index(flag) + 1] = str(value)
    bindings = dict(previous['bindings'])
    for path in (Path(__file__).resolve(), root / 'request.json'):
        bindings[str(path)] = digest(path)
    write(root / 'plan.json', dict(
        commands=dict(candidate=command, comparison=compare), bindings=bindings,
        reason=('Predeclared bracketed v3 replay after the original reference; '
                'retain both observations'),
        reference_reused_for_comparison=True, sequence='v3-before, original, v3-after',
        production_modified=False, qualified_speedup=None))
    execute(root, 'candidate', command)
    execute(root, 'comparison', compare, allowed=(2,))
    for name, sha in bindings.items():
        assert digest(name) == sha, name
    result = read(root / 'comparison.json')
    assert result['all_checked_values_exact'] and not result['errors']
    assert not result['missing_audit_mappings'] and len(result['mapped_policies']) == 17
    clock = read(root / 'cli/attempt/supervisor.json')
    print(json.dumps(dict(exact=True, seconds=clock['process_seconds'])), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, required=True)
    main(parser.parse_args().parent.resolve())
