"""Additive immutable provenance for the already frozen numerical driver."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy
import scipy
import run_full
import repair_algo04_empty_audit  # Load its historical audit adapters before inspection.

OUT = run_full.OUT
ROOT = run_full.ROOT
SOURCE = run_full.SOURCE
SEAL = OUT/'dependency_seal.json'
SELF = Path(__file__).resolve()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_files(files):
    for name, expected in files.items():
        path = Path(name)
        if not path.is_file() or digest(path) != expected:
            raise ValueError('dependency bytes changed: '+name)


def dependencies():
    roots = [ROOT/'tools', ROOT/'src', SOURCE/'source/tools', Path('/tmp/algo03-feasible-deps')]
    explicit = {SELF, Path(run_full.__file__).resolve(), Path(run_full.exp.__file__).resolve()}
    paths = set(explicit)
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if not name:
            continue
        path = Path(name).resolve()
        if path.suffix == '.py' and any(path.is_relative_to(root.resolve()) for root in roots):
            paths.add(path)
    return {str(path): digest(path) for path in sorted(paths)}


def verify_archived_provenance(files):
    protocol = json.loads((SOURCE/'protocol.json').read_text())
    core = {str(ROOT/'tools'/(name+'.py')): value for name, value in protocol['source_hashes'].items()}
    verify_files(core)
    archive = json.loads((SOURCE/'evidence/source_hashes.json').read_text())
    verify_files({str(SOURCE/name): value for name, value in archive.items()})
    compared = []
    for name, value in files.items():
        path = Path(name)
        if path.is_relative_to(ROOT/'tools'):
            archived = SOURCE/'source/upstream_tools'/path.relative_to(ROOT/'tools')
            if archived.is_file():
                if digest(archived) != value:
                    raise ValueError('import differs from archived upstream: '+name)
                compared.append(name)
    return dict(core_files=len(core), archived_files=len(archive), imported_upstream_matches=sorted(compared))


def create():
    files = dependencies()
    record = dict(schema_version=1, protocol_sha256=digest(OUT/'protocol.json'),
                  seal_source_sha256=digest(SELF), files=files,
                  python_version=sys.version, numpy_version=numpy.__version__, scipy_version=scipy.__version__,
                  archived_provenance=verify_archived_provenance(files))
    # Exclusive creation preserves a prior seal, including when another process races.
    with SEAL.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return record


def check():
    record = json.loads(SEAL.read_text())
    if digest(SELF) != record['seal_source_sha256']:
        raise ValueError('dependency seal source changed')
    if digest(OUT/'protocol.json') != record['protocol_sha256']:
        raise ValueError('frozen protocol changed')
    verify_files(record['files'])
    if dependencies() != record['files']:
        raise ValueError('imported dependency inventory changed')
    for key, actual in [('python_version', sys.version), ('numpy_version', numpy.__version__), ('scipy_version', scipy.__version__)]:
        if record[key] != actual:
            raise ValueError(key+' changed')
    return record


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--create', action='store_true')
    group.add_argument('--check', action='store_true')
    args = parser.parse_args()
    record = create() if args.create else check()
    print(('Created' if args.create else 'Verified')+' dependency seal: '+str(len(record['files']))+' files')


if __name__ == '__main__':
    main()
