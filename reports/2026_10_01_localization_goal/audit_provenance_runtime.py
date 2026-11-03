"""Record actual installed detector source paths; additive post-export audit."""
import argparse
import hashlib
import inspect
import json
from pathlib import Path

import leo.analysis.persistent_hop_trajectory as trajectory
import leo.application.scanner_trajectory as projection


def digest(path):
    return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    module_path = Path(inspect.getsourcefile(trajectory)).resolve()
    package = module_path.parents[1]
    release = package.parents[4]
    assert release.name == '17484895464c225ebba977487aa36d3d81658bd8'
    sources = {str(p): digest(p) for p in sorted(package.rglob('*.py'))}
    comparisons = []
    for module in [trajectory, projection]:
        installed = Path(inspect.getsourcefile(module)).resolve()
        source = release/'src/leo'/installed.relative_to(package)
        comparisons.append(dict(installed=str(installed), source=str(source),
                                installed_sha256=digest(installed), source_sha256=digest(source)))
        assert digest(installed) == digest(source)
    result = dict(source_sha256=sources, comparisons=comparisons, auditor_sha256=digest(Path(__file__)),
                  qualification='Additive source snapshot recorded after detector exports. '
                  'Original exporter only captured its own source because it filtered /src/leo/. '
                  'This captures the actual site-packages tree now; it cannot retroactively '
                  'prove every file was unchanged at export time. Inspected trajectory and '
                  'projection modules match pinned release sources byte-for-byte.')
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print(json.dumps(dict(output=str(args.output), sha256=digest(args.output), files=len(sources))))


if __name__ == '__main__':
    main()
