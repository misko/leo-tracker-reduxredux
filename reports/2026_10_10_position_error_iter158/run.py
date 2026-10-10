"""Thin successor orchestration over155's frozen clean reconstruction ports."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent/'2026_10_10_position_error_iter155'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


#155 run.py imports only standard-library modules until dependencies() is called.
BASE = module('run155_for158', PRIOR/'run.py')


def wrap_ports(ports, check, *, clock=time.monotonic):
    """Start deadline before endpoint construction, after member input loading."""
    original = ports['reconstruct']
    state = {}
    def reconstruct(*args, **kwargs):
        state['begun'] = clock()
        return original(*args, **kwargs)
    def diagnostic(*args, **kwargs):
        if 'begun' not in state:
            raise ValueError('endpoint reconstruction must precede diagnostic')
        return check(*args, **kwargs, begun=state['begun'], clock=clock)
    return dict(ports, reconstruct=reconstruct, check=diagnostic)


def dependencies(member):
    # All scientific imports follow verify(), including inherited dependencies.
    if str(PRIOR) not in sys.path:
        sys.path.insert(0, str(PRIOR))
    ports = BASE.dependencies(member)
    endpoint = module('endpoint158', HERE/'endpoint.py')
    return wrap_ports(ports, endpoint.check)


def evaluate_member(member):
    return BASE.evaluate_member(member, dependency_factory=dependencies)


def run_member(member, directory, digest, *, evaluate=evaluate_member):
    folder = Path(directory)
    result = folder/(member['label']+'.json')
    if result.exists():
        claim = json.loads((folder/(member['label']+'.claim.json')).read_text())
        if claim.get('label') != member['label'] or claim.get('protocol_sha256') != digest:
            raise ValueError('terminal receipt lacks matching claim')
    return BASE.run_member(member, directory, digest, evaluate=evaluate)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('shard', type=int, choices=(0,1))
    parser.add_argument('--protocol', type=Path, default=HERE/'protocol.json')
    parser.add_argument('--output', type=Path, default=HERE/'results')
    args = parser.parse_args()
    # Load this policy by absolute filename:155 dependencies later add their path.
    freezer = module('freeze158', HERE/'freeze.py')
    plan = json.loads(args.protocol.read_text())
    BASE.verify(plan, freezer.POLICY)
    from leo.contracts.digests import canonical_digest
    digest = canonical_digest(plan)
    for member in plan['members'][args.shard::2]:
        row = run_member(member, args.output, digest)
        print(member['label'], row['status'], flush=True)


if __name__ == '__main__':
    main()
