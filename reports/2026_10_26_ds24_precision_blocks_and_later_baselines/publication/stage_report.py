"""Stage exact compact publication bytes locally; never mutate the publisher."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LATER = Path('/srv/bulk/leo/research/ds24-later-four-preparation-r01')
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT = Path('reports/2026_10_26_ds24_precision_blocks_and_later_baselines')
STAGE = HERE / 'stage'
LIMIT = 1_000_000
SKIP = {'publication', '__pycache__', '.pytest_cache', '.git'}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def manifest_paths(path):
    manifest = read(path)
    base = Path(manifest.get('root', path.parent))
    selected = {}
    for row in manifest['published']:
        source = Path(row['path'])
        source = source if source.is_absolute() else base / source
        if sha(source) != row['sha256']:
            raise ValueError('lean-manifest source changed: ' + str(source))
        selected[source.resolve()] = row['sha256']
    selected[path.resolve()] = sha(path)
    return selected


def prerequisites():
    for name in ('README.md',):
        if not (ROOT / name).is_file():
            raise ValueError('final root document not present: ' + name)
    seal_path = ROOT / 'audit/final_seal.json'
    seal = read(seal_path)
    if not seal['all_passed']:
        raise ValueError('final independent audit must pass')
    for name, digest in seal['files'].items():
        if sha(name) != digest:
            raise ValueError('final audit binding changed: ' + name)
    for path in (LATER / 'prepared/preparation_execution.json',
                 LATER / 'baseline/later_execution.json'):
        status = read(path)
        if not status['terminal'] or not status['all_four_slots_preserved']:
            raise ValueError('all four terminal slots required: ' + str(path))
    # Nomination may legitimately block some members; its terminal seal, not
    # successful selection of every owner, is the publication prerequisite.
    nomination = LATER / 'baseline/nomination'
    if not (nomination / 'RF_seal.json').exists():
        raise ValueError('terminal nomination seal not present')
    if not read(nomination / 'summary.json')['all4_slots_terminal']:
        raise ValueError('all four nomination slots must remain terminal')
    if not (ROOT / 'mechanism/FINDINGS.md').is_file():
        raise ValueError('final mechanism findings not present')
    return seal_path


def case_receipt(relative):
    if len(relative.parts) != 2 or not relative.parts[0].startswith('LATER4-'):
        return False
    return relative.name in {'input_receipt.json', 'prepared.json', 'receipt.json',
                             'preparation_receipt.json'}


def baseline_compact(relative, path):
    if relative.parts[0] == 'work':
        inner = Path(*relative.parts[1:])
        return (len(inner.parts) == 1 and path.suffix in {'.json', '.stdout', '.stderr'}
                or case_receipt(inner))
    return path.suffix != '.npz' and path.stat().st_size <= LIMIT


def main():
    seal_path = prerequisites()
    if STAGE.exists():
        raise FileExistsError('preserve the existing stage; do not overwrite a frozen package')
    mechanism = manifest_paths(ROOT / 'mechanism/lean_publication.json')
    baseline_manifest = LATER / 'baseline/lean_publication.json'
    baseline_selected = manifest_paths(baseline_manifest) if baseline_manifest.exists() else None
    candidates = []
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if not path.is_file() or SKIP.intersection(relative.parts):
            continue
        if path.name in {'publication_receipt.json', 'publication_checks.json'}:
            continue
        include = (path.resolve() in mechanism if relative.parts[0] == 'mechanism'
                   else path.suffix != '.npz' and path.stat().st_size <= LIMIT)
        candidates.append((path, relative, include))
    # Include this exact publication source as well, without recursively staging
    # its generated output directory or copying anything into the publisher.
    candidates.append((Path(__file__), Path('publication/stage_report.py'), True))
    for branch in ('readiness', 'prepared', 'baseline'):
        base = LATER / branch
        for path in base.rglob('*'):
            local = path.relative_to(base)
            if not path.is_file() or SKIP.intersection(local.parts):
                continue
            if branch == 'readiness':
                include = path.suffix != '.npz' and path.stat().st_size <= LIMIT
            elif branch == 'prepared':
                include = ((len(local.parts) == 1 and path.suffix in {'.json', '.md', '.stdout', '.stderr'})
                           or case_receipt(local)) and path.stat().st_size <= LIMIT
            else:
                include = (path.resolve() in baseline_selected if baseline_selected is not None
                           else baseline_compact(local, path))
            candidates.append((path, Path('later') / branch / local, include))
    STAGE.mkdir()
    included, external = {}, {}
    for source, relative, include in sorted(candidates, key=lambda row: str(row[1])):
        if source.is_symlink():
            raise ValueError('publication source must be an ordinary file: ' + str(source))
        record = dict(source=str(source), bytes=source.stat().st_size, sha256=sha(source))
        if not include:
            external[str(relative)] = record
            continue
        if str(relative) in included:
            raise ValueError('duplicate destination: ' + str(relative))
        target = STAGE / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha(target) != record['sha256']:
            raise ValueError('copy changed bytes: ' + str(relative))
        included[str(relative)] = record
    manifest = dict(report=str(REPORT), included=included, external=external,
        audit_seal_sha256=sha(seal_path), external_inputs_required=True,
        scientific_execution=False, publisher_mutated=False,
        note='Compact research report; raw GLRT, banks, full retained parents and source dependencies remain external and hash-bound by the copied protocols/seals. No IQ is included.')
    write(STAGE / 'publication_manifest.json', manifest)
    checked, missing = [], []
    for path in sorted(STAGE.rglob('*.md')):
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = unquote(raw.strip().strip('<>').split('#', 1)[0])
            if not target or target.startswith(('https:', 'http:', 'mailto:', '/')):
                continue
            row = dict(file=str(path.relative_to(STAGE)), target=target)
            local = (path.parent / target).resolve()
            if local.is_relative_to(STAGE) and local.exists():
                row['authority'] = 'staged exact file/tree'
                checked.append(row)
                continue
            final = (PUBLISHER / REPORT / path.relative_to(STAGE).parent / target).resolve()
            if final.is_relative_to(PUBLISHER):
                result = subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + str(final.relative_to(PUBLISHER))],
                                        cwd=PUBLISHER, capture_output=True)
                if result.returncode == 0:
                    row['authority'] = 'publisher full git HEAD'
                    checked.append(row)
                    continue
            missing.append(row)
    checks = dict(files=len(included) + 1,
                  bytes=sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file()),
                  external_files=len(external), checked_relative_links=checked,
                  missing_links=missing, ready=not missing, stage=str(STAGE), report=str(REPORT),
                  manifest_sha256=sha(STAGE / 'publication_manifest.json'))
    write(HERE / 'checks.json', checks)
    print(json.dumps({k: v for k, v in checks.items() if k != 'checked_relative_links'}))
    if missing:
        raise ValueError('publication relative links need review; science bytes were not changed')


if __name__ == '__main__':
    main()
