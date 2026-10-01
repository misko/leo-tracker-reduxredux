"""Derive an explicitly labelled first-start replay receipt; never fit or score geography."""
import time
START = time.monotonic()
import argparse
from copy import deepcopy
import json
from pathlib import Path
import resource

from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def first_start_receipt(original, parent_path, parent_hash):
    result = deepcopy(original)
    fits = original['fits']
    if fits and fits[0]['seed_index'] != 0:
        raise ValueError('Missing acquisition-ranked first start')
    first = deepcopy(fits[0]) if fits else None
    result['fits'] = [first] if first else []
    result['best'] = first if first and first['objectives'] else None
    result['status'] = 'converged_local_mode' if result['best'] and first['converged'] else 'unresolved'
    result['config']['seed_limit'] = 1
    result['qualification'] = 'Saved first-start replay only; process time is materialization, not inference. Independent numerical audit required. No geographic selection, continuation or fallback.'
    result['replay'] = dict(parent_path=str(parent_path), parent_sha256=parent_hash,
                          selected_seed_index=0, original_wall_seconds=original['wall_seconds'],
                          original_cpu_seconds=original['cpu_seconds'],
                          original_first_fit_seconds=first['seconds'] if first else None,
                          recorded_later_fit_seconds=sum(f['seconds'] for f in fits[1:]))
    # Caller supplies actual materialization process costs before writing.
    result['wall_seconds'] = None
    result['cpu_seconds'] = None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('unit')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    selection = sealed(HERE/'selection.json')
    binding = next(u for u in selection['evaluation_units'] if u['unit_id'] == args.unit)
    parent = HERE/'independent-v2'/binding['block_id']/(args.unit+'.json')
    original = sealed(parent)
    if original['binding'] != binding:
        raise ValueError('Selection/parent mismatch')
    for mapping in ('source_sha256', 'inputs'):
        for path, expected in original[mapping].items():
            if digest(path) != expected:
                raise ValueError(f'Changed parent source/input: {path}')
    result = first_start_receipt(original, parent, digest(parent))
    for name in ('materialize_first_start.py', 'screen_seed_prefix.py'):
        result['source_sha256'][str(HERE/name)] = digest(HERE/name)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    result.update(wall_seconds=time.monotonic()-START, cpu_seconds=usage.ru_utime+usage.ru_stime)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    args.output.with_suffix('.sha256').write_text(digest(args.output)+'\n')


if __name__ == '__main__':
    main()
