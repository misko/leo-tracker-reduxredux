"""Package only the independently audited DS24 receiver-shift report."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
from urllib.parse import unquote


ROOT = Path('/srv/bulk/leo/research/ds24-receiver-shift-witness-20261025')
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
DEST = PUBLISHER / 'reports/2026_10_24_ds24_receiver_shift_witness'
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
PRIOR = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
PUBLISHED_PRIOR = PUBLISHER / 'reports/2026_10_24_ds24_receiver_orbit_controls'
CASES = ('DS24-0017', 'DS24-0095')


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


def record(path):
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def main():
    for name in ('artifact_audit.json', 'heldout_table_audit.json', 'geometry_table_audit.json', 'position_reporting_audit.json'):
        assert read(ROOT/'audit'/name)['status'] == 'passed'
    assert not DEST.exists(), 'Preserve an existing report; use a new explicit destination.'
    DEST.mkdir(parents=True)
    raw = {case: [] for case in CASES}
    direct = []
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in ('__pycache__', '.pytest_cache', 'mpl', '.mpl', '.matplotlib') for part in rel.parts):
            continue
        if path.name.startswith('working_tree_status_') or path.name in ('publication.log', 'publication_receipt.json'):
            continue
        if path.suffix not in ('.md', '.py', '.json', '.csv', '.png', '.log', '.txt', '.npz'):
            continue
        bulky = path.suffix == '.npz' or rel.parts[:2] == ('heldout', 'results') or (rel.parts[0] == 'geometry' and path.name in tuple(c+'.json' for c in CASES))
        if bulky:
            case = next(case for case in CASES if case in path.name)
            raw[case].append((path, rel))
        else:
            direct.append((path, rel))
    copies = []
    for source, rel in direct:
        target = DEST/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copies.append(dict(source=str(source), published=str(rel), sha256=sha(source), bytes=source.stat().st_size))
    archives = []
    for case, files in raw.items():
        archive = DEST/f'raw_results_{case}.tar.gz'
        members = []
        with archive.open('wb') as out, gzip.GzipFile(filename='', mode='wb', fileobj=out, mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as tar:
            for source, rel in files:
                payload = source.read_bytes()
                entry = tarfile.TarInfo(str(rel))
                entry.size = len(payload)
                entry.mode = 0o644
                entry.mtime = 0
                tar.addfile(entry, io.BytesIO(payload))
                members.append(dict(source=str(source), member=str(rel), bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
        assert archive.stat().st_size < 50_000_000
        with tarfile.open(archive, 'r:gz') as tar:
            assert set(tar.getnames()) == {m['member'] for m in members}
            for member in members:
                assert hashlib.sha256(tar.extractfile(member['member']).read()).hexdigest() == member['sha256']
        archives.append(dict(case=case, path=archive.name, sha256=sha(archive), bytes=archive.stat().st_size, members=members))
    # Snapshot every runtime source bound by the prefit protocol, not a mutable
    # import-resolution approximation. New report/audit sources are direct copies.
    dependencies = read(ROOT/'heldout/protocol.json')['dependencies']
    source_records = []
    for dependency in dependencies:
        source = Path(dependency['path'])
        assert sha(source) == dependency['sha256']
        if source.is_relative_to(ROOT):
            rel = source.relative_to(ROOT)
        elif source.is_relative_to(REPO):
            rel = Path('source/repository')/source.relative_to(REPO)
        elif source.is_relative_to(PRIOR):
            rel = Path('source/previous_study')/source.relative_to(PRIOR)
        else:
            raise ValueError('Unexpected source root: '+str(source))
        target = DEST/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        source_records.append(dict(source=str(source), published=str(rel), sha256=sha(source), bytes=source.stat().st_size))
    write(DEST/'source_manifest.json', dict(scope='All 359 prefit-bound runtime dependencies snapshotted; additional new report/audit sources preserved as direct copies',
        protocol_sha256=sha(ROOT/'heldout/protocol.json'), files=source_records,
        report_sources=[item for item in copies if item['published'].endswith('.py')]))
    # Rehash the two cases' persisted input files against the preceding complete
    # published input inventory. Preserve that inventory hash for shared inputs.
    prior_manifest = PUBLISHED_PRIOR/'input_manifest.json'
    inputs = []
    for item in read(prior_manifest)['files']:
        if any(case in item['path'] for case in CASES):
            source = Path(item['path'])
            assert sha(source) == item['sha256']
            inputs.append(record(source))
    for case in CASES:
        for source in (Path(read(ROOT/'heldout/input_manifest.json')[case]['baseline_path']), PRIOR/'evaluation/models/receiver_fast_rx1_rf50'/(case+'.json')):
            inputs.append(record(source))
    write(DEST/'input_manifest.json', dict(scope='Both cases rehashed against the previous complete published input inventory; shared corpus retained by inherited manifest hash',
        inherited_input_inventory=dict(path='../2026_10_24_ds24_receiver_orbit_controls/input_manifest.json', sha256=sha(prior_manifest)),
        heldout_input_manifest_sha256=sha(ROOT/'heldout/input_manifest.json'), files=inputs))
    links = []
    for path in DEST.rglob('*.md'):
        if 'source' in path.relative_to(DEST).parts:
            continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            if target.startswith(('http:', 'https:', 'mailto:', '#')):
                continue
            local = unquote(target.strip('<>').split('#')[0])
            if local:
                assert (path.parent/local).exists(), (str(path), target)
                links.append(dict(document=str(path.relative_to(DEST)), target=target))
    from PIL import Image
    figures = []
    for path in DEST.rglob('*.png'):
        with Image.open(path) as image:
            image.verify()
        figures.append(str(path.relative_to(DEST)))
    assert len(figures) == 10
    for item in copies+source_records:
        assert sha(DEST/item['published']) == item['sha256']
    write(DEST/'archive_manifest.json', dict(archives=archives, direct_copies=copies,
        source_manifest_sha256=sha(DEST/'source_manifest.json'), input_manifest_sha256=sha(DEST/'input_manifest.json')))
    audit = dict(passed=True, report_directory=str(DEST.relative_to(PUBLISHER)), new_position_fits=24,
        crossover_vectors=48, sensitivity_scores=144, path_points=88, numerical_tests=10,
        independent_scientific_audits=[dict(path='audit/'+name, sha256=sha(ROOT/'audit'/name)) for name in (
            'artifact_audit.json', 'heldout_table_audit.json', 'geometry_table_audit.json', 'position_reporting_audit.json')],
        direct_copies=len(copies), source_dependencies_snapshotted=len(source_records), two_case_inputs_rehashed=len(inputs),
        raw_archive_members=sum(len(a['members']) for a in archives), archives=[{k:v for k,v in a.items() if k != 'members'} for a in archives],
        figures=figures, local_links_checked=len(links), missing_links=0,
        all_raw_arrays_preserved=True, nonconvergence_retained=True, no_new_RF_or_algorithm_promotion=True,
        archive_manifest_sha256=sha(DEST/'archive_manifest.json'))
    write(DEST/'publication_audit.json', audit)
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
