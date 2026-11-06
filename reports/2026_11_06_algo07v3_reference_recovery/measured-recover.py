"""Reconstruct historical bytecode only when every byte matches its original hash.

No manifest, source or golden output is changed. Candidate compilation and
timestamp headers are accepted only by the pre-existing SHA-256 commitment.
"""

import argparse
import hashlib
import importlib.util
import json
import marshal
import struct
import subprocess
from pathlib import Path


REVISIONS = {
    'analysis/research/continuous_curve_fit': ('36ff79029', False),
    'analysis/research/orbit_uncertainty': ('36ff79029', False),
    'application/__init__': ('fb6c4454a', False),
    'operations/causal_tle_catalogue': ('a0fc93416', False),
    'presentation/fast_standard_analysis': ('feb1f70da', True),
    'storage/fast_scan': ('38f21ac02', False),
    'storage/fast_standard_analysis': ('feb1f70da', False),
}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def main(output, search_days):
    repo = Path.cwd().resolve()
    output.mkdir(exist_ok=False)
    manifest = Path('/srv/bulk/leo/research/algo07-star-20261104/iteration000/frozen-r2.json')
    frozen = json.loads(manifest.read_bytes())
    files = {r['path']: r for r in frozen['files']}
    timestamps = set()
    for row in frozen['files']:
        path = Path(row['path'])
        if '/src/leo/' not in str(path):
            continue
        if path.is_file():
            timestamps.add(int(path.stat().st_mtime))
            if path.suffix == '.pyc':
                head = path.read_bytes()[:16]
                if len(head) == 16 and struct.unpack('<I', head[4:8])[0] == 0:
                    timestamps.add(struct.unpack('<I', head[8:12])[0])
    # Nearby seconds account for files copied in the same small checkout batch.
    timestamps = sorted({t + offset for t in timestamps for offset in range(-3, 4)
                         if 0 <= t + offset < 2**32})
    if search_days:
        end = frozen['created_utc_ns'] // 1_000_000_000
        timestamps.extend(range(end - search_days * 86400, end + 1))
    results = []
    for name, (revision, relative) in REVISIONS.items():
        source_path = repo / 'src/leo' / (name + '.py')
        target = source_path.parent / '__pycache__' / (source_path.stem + '.cpython-312.pyc')
        expected = files[str(target)]
        commit = subprocess.check_output(['git', 'rev-parse', revision], text=True).strip()
        source = subprocess.check_output(['git', 'show', f'{commit}:{source_path.relative_to(repo)}'])
        filename = str(source_path.relative_to(repo) if relative else source_path)
        code = compile(source, filename, 'exec', dont_inherit=True, optimize=0)
        body = marshal.dumps(code)
        assert len(body) + 16 == expected['bytes'], name
        row = dict(target=str(target), revision=commit, source_sha256=digest(source),
                   compiled_filename=filename, expected_sha256=expected['sha256'],
                   candidates=len(timestamps), recovered=False)
        for timestamp in timestamps:
            candidate = (importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, timestamp, len(source))
                         + body)
            if digest(candidate) == expected['sha256']:
                path = output / target.relative_to(repo)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(candidate)
                row.update(recovered=True, source=str(path), timestamp=timestamp,
                           sha256=digest(path.read_bytes()))
                break
        results.append(row)
        print(json.dumps(row), flush=True)
    receipt = dict(manifest=str(manifest), manifest_sha256=digest(manifest.read_bytes()),
                   script_sha256=digest(Path(__file__).read_bytes()), results=results,
                   all_exact=all(r['recovered'] for r in results), fixture_changed=False)
    (output / 'recovery.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--search-days', type=int, choices=range(8), default=0)
    args = parser.parse_args()
    main(args.output.resolve(), args.search_days)
