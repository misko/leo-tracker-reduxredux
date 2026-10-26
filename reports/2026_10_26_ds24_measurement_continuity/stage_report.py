"""Assemble a compact report after final scientific audits; no inference calls."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
REPORT = Path('reports/2026_10_26_ds24_measurement_continuity')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    for name in ('README.md', 'measurement/FINDINGS.md', 'prediction/FINDINGS.md', 'recorded/FINDINGS.md', 'attribution/FINDINGS.md'):
        if not (ROOT/name).is_file():
            raise FileNotFoundError(name)
    audit_path = ROOT/'audit/final_seal.json'
    audit = json.loads(audit_path.read_text())
    assert audit['all_passed'] and audit['passed_receipts'] >= 6
    for name, digest in audit['files'].items():
        assert sha(Path(name)) == digest, name
    receipts = []
    for name in ('measurement_preflight', 'measurement_terminal', 'prediction_preflight02',
                 'prediction_terminal02', 'attribution', 'recorded_readback'):
        path = ROOT/'audit'/f'{name}.json'
        assert json.loads(path.read_text())['all_passed']
        receipts.append(dict(path=str(path), sha256=sha(path)))
    terminal = dict(all_passed=True, receipts=receipts,
                    audit_seal_sha256=sha(audit_path), scientific_execution=False,
                    complete_position_slots=0, complete_prediction_slots=8,
                    complete_IQ_slots=70, complete_graph_sequences=4, operational_policy='exact_original_reference')
    (ROOT/'terminal_checks.json').write_text(json.dumps(terminal, indent=2)+'\n')
    selected = {}
    for branch in ('measurement', 'prediction'):
        manifest_path = ROOT/branch/'lean_publication.json'
        manifest = json.loads(manifest_path.read_text())
        branch_files = {row['path']: row['sha256'] for row in manifest['published']}
        for name, digest in branch_files.items():
            assert sha(Path(name)) == digest, name
        selected[branch] = branch_files
    stage = ROOT/'publication'
    stage.mkdir(exist_ok=False)
    included, external = {}, {}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or {'publication', '__pycache__', '.pytest_cache'}.intersection(rel.parts)
                or path.name in {'publication_receipt.json', 'publication_checks.json'}):
            continue
        record = dict(source=str(path), bytes=path.stat().st_size, sha256=sha(path))
        branch = rel.parts[0]
        bulky = ((branch not in selected and path.suffix in {'.npy', '.npz'}) or
                 (branch in selected and str(path) not in selected[branch]
                  and path.name != 'lean_publication.json'))
        if bulky:
            external[str(rel)] = record
            continue
        destination = stage/rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        assert sha(destination) == record['sha256'], str(rel)
        included[str(rel)] = record
    manifest = dict(included=included, external=external, report=str(REPORT),
                    external_inputs_required=True, scientific_execution=False)
    (stage/'publication_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    checked, missing = [], []
    for path in stage.rglob('*.md'):
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            target = target.strip().strip('<>').split('#', 1)[0]
            if not target or target.startswith(('http:', 'https:', 'mailto:', '/')):
                continue
            record = dict(file=str(path.relative_to(stage)), target=target)
            if (path.parent/target).resolve().is_file():
                checked.append(record)
                continue
            final = (PUBLISHER/REPORT/path.relative_to(stage).parent/target).resolve()
            try:
                relative = final.relative_to(PUBLISHER)
                result = subprocess.run(['git', 'cat-file', '-e', 'HEAD:'+str(relative)],
                                        cwd=PUBLISHER, capture_output=True)
            except ValueError:
                result = None
            (checked if result is not None and result.returncode == 0 else missing).append(record)
    checks = dict(files=len(included)+1, bytes=sum(v['bytes'] for v in included.values()),
                  external_files=len(external), checked_relative_links=checked,
                  missing_links=missing, ready=not missing,
                  manifest_sha256=sha(stage/'publication_manifest.json'))
    (ROOT/'publication_checks.json').write_text(json.dumps(checks, indent=2)+'\n')
    print(json.dumps({k:v for k,v in checks.items() if k != 'checked_relative_links'}))
    if missing:
        raise ValueError('Broken report links')


if __name__ == '__main__':
    main()
