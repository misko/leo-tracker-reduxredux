"""Copy compact, hash-bound DS27 evidence; never bundle private inference exports.

The default updates reproduction sources, compact proof receipts and stable
results. Final manifest creation is explicit, after the author finishes README
and gallery files. Gzip output has an empty filename and fixed mtime zero.
"""

import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path

STUDY = Path(__file__).resolve().parent
REPOSITORY = Path('/srv/bulk/leo-dev/fast-algo02-production-v1')
DESTINATION = REPOSITORY / 'reports/2026_10_31_ds27_algo04_review'
RELEASE = Path('/opt/leo-fast-graph/f9e262f96b6e2e75b397f69d50a0ea9104e293ef')
BASELINE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/runtime-baseline-production')
CANDIDATE = Path('/srv/bulk/leo/research/algo03-full-evaluation-20261030/runtime-candidate')
THRESHOLD = 128 * 1024


def sha(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def deterministic_gzip(value):
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0, compresslevel=9) as stream:
        stream.write(value)
    return output.getvalue()


def checked_relative(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError('Unsafe publication artifact path')
    if any(p in ('source-export', 'public-algo03-export', 'private-export', '__pycache__') for p in path.parts):
        raise ValueError('Private inference exports are not publication artifacts')
    if path.suffix.lower() in ('.npz', '.npy', '.iq', '.qin', '.bin'):
        raise ValueError('Full numerical arrays and radio payloads are excluded')
    return path


def publish_bytes(source, raw, destination, relative, *, transform='byte_copy', source_sha256=None):
    relative = checked_relative(relative)
    payload = raw
    if relative.suffix == '.json' and len(raw) >= THRESHOLD:
        payload = deterministic_gzip(raw)
        relative = Path(str(relative) + '.gz')
        transform = 'deterministic_gzip' if transform == 'byte_copy' else transform + '+deterministic_gzip'
    target = destination / relative
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Publication target traverses a symbolic link')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_bytes() != payload:
        target.write_bytes(payload)
    return dict(source_path=str(source), source_sha256=source_sha256 or sha(raw),
                published_path=relative.as_posix(), published_sha256=sha(payload),
                published_content_sha256=sha(raw), transform=transform,
                source_bytes=Path(source).stat().st_size, published_bytes=len(payload))


def copy_artifact(source, destination, relative):
    source = Path(source)
    if any(p.is_symlink() for p in (source, *source.parents)):
        raise ValueError('Publication source traverses a symbolic link')
    raw = source.read_bytes()
    record = publish_bytes(source, raw, destination, relative)
    if source.read_bytes() != raw:
        raise ValueError('Publication source changed while copying: ' + str(source))
    return record


def compact_public_jobs(source):
    """Retain public job inputs and receipt hashes without duplicate envelopes."""
    records = read(source)
    return dict(schema='ds27-public-algo03-job-map-compact/v1', original_file_sha256=sha(source.read_bytes()),
                original_records=len(records), omitted_job_fields=['result'], records=[
                    dict(record, job={key: value for key, value in record['job'].items() if key != 'result'})
                    for record in records])


def bundle(study=STUDY, destination=DESTINATION, *, include_failed_native=False, manifest=False):
    destination.mkdir(parents=True, exist_ok=True)
    records = []

    def add(source, relative):
        records.append(copy_artifact(source, destination, relative))

    sources = (
        'offline_algo04.py', 'test_offline_algo04.py', 'coordinate_evaluation.py', 'test_coordinate_evaluation.py',
        'build_analysis_index.py', 'test_build_analysis_index.py', 'inventory_public_inputs.py',
        'test_inventory_public_inputs.py', 'report_ds27.py', 'test_report_ds27.py',
        'rank_native_residuals.py', 'test_rank_native_residuals.py',
        'audit_top_fragments.py', 'test_audit_top_fragments.py',
        'audit_causal_initialization.py', 'test_audit_causal_initialization.py',
        'audit_inventory_publication.py', 'test_audit_inventory_publication.py',
        'audit_parent_extras.py', 'test_audit_parent_extras.py',
        'bundle_publication.py', 'test_bundle_publication.py')
    for name in sources:
        add(study / name, 'reproduction/' + name)
    add(REPOSITORY / 'tools/run_algo03_dataset_evaluation.py', 'reproduction/run_algo03_dataset_evaluation.py')
    for name in ('algo04_numerical_helper.py', 'algo04_numerical_stage.py', 'algo04_annotation_replay.py',
                 'algo04_cache.py', 'algo04_replay_worker.py', 'algo04_production_worker.py', 'stage_algo04_release.py'):
        add(RELEASE / 'tools' / name, 'reproduction/installed-algo04/tools/' + name)
    for name in ('fast_graph_position_v3.py',):
        add(RELEASE / 'src/leo/contracts' / name, 'reproduction/installed-algo04/src/leo/contracts/' + name)
    for name in ('test_algo04_numerics.py', 'test_algo04_replay.py', 'test_algo04_production_worker.py'):
        add(REPOSITORY / 'tests/tools' / name, 'reproduction/installed-algo04/tests/tools/' + name)
    for root, name in ((BASELINE, 'baseline'), (CANDIDATE, 'candidate')):
        add(root / 'runtime-freeze.json', 'proofs/runtime-' + name + '-freeze.json')
    add(RELEASE / 'release-manifest.json', 'proofs/installed-algo04-release-manifest.json')
    add(RELEASE / 'reports/ALGO04/releases/2026-10-31-r1/manifest.json', 'proofs/installed-algo04-scientific-manifest.json')
    for name in (
        'inventory-cutoff.json', 'inventory-integrity.json', 'inventory-freeze-seal.json',
        'input-availability.json', 'public-input-map.json', 'completed-algo02-job-map.json',
        'input-availability-seal.json', 'runtime-hashes.json', 'evaluation-protocol.json',
        'evaluation-launch.json', 'evaluation-progress.json', 'evaluation-seal.json',
        'analysis-index.json', 'analysis-seal.json', 'ranking-protocol.json',
        'ranking-tooling-extension-receipt.json', 'DS27-0018-read-audit-diagnostic.json'):
        add(study / name, 'proofs/' + name)
    for name in ('residual-audit-seal.json', 'plot-reproduction.json'):
        add(study / name, 'proofs/' + name)
    if (study / 'final-test-summary.json').is_file():
        add(study / 'final-test-summary.json', 'proofs/final-test-summary.json')
    for name in ('RANKING_TOOLING.md', 'RESIDUAL_TRACK_AUDIT.md'):
        add(study / name, name)
    add(study / 'datasets/DS27.json', 'proofs/datasets/DS27.json')
    source = study / 'completed-algo03-job-map.json'
    records.append(publish_bytes(source, json_bytes(compact_public_jobs(source)), destination,
        'proofs/completed-algo03-job-map.compact.json', transform='omit_redundant_job_result_envelopes',
        source_sha256=sha(source.read_bytes())))
    for name in ('dataset-freeze.log', 'public-input-inventory.log', 'evaluation-coordinator.log'):
        add(study / name, 'reproduction/logs/' + name)
    for case in read(study / 'evaluation-protocol.json')['fast_cases']:
        for source_name, published_name in (('pipeline-receipt.json', 'pipeline-receipt.json'),
                                             ('candidate-v3/receipt.json', 'ALGO04-receipt.json')):
            source = study / 'cases' / case / source_name
            add(source, 'proofs/cases/' + case + '/' + published_name)
        inference = study / 'cases' / case / 'candidate-v3/inference-seal.json'
        if inference.is_file():
            add(inference, 'proofs/cases/' + case + '/ALGO04-inference-seal.json')
    for name in ('causal-initialization-audit.json', 'causal-initialization-audit.md',
                 'inventory-publication-audit.json', 'inventory-publication-audit.md'):
        add(study / name, 'audits/' + name)
    for directory in ('results', 'residual-ranking', 'top10-annotation-audit', 'parent-extra-audit'):
        for source in sorted((study / directory).rglob('*')):
            if source.is_file() and source.suffix in ('.json', '.gz', '.csv', '.png', '.pdf', '.md'):
                add(source, source.relative_to(study))
    if include_failed_native:
        for name in ('failed-native-index.json',):
            add(study / name, 'proofs/' + name)
        for name in ('failed-scan-DS27-0006-longest3.png', 'failed-scan-native-inventory.json',
                     'plot-inputs.json.gz'):
            source = study / 'failed-native-ranking' / name
            add(source, source.relative_to(study))
    records.sort(key=lambda record: record['published_path'])
    artifact_map = dict(schema='ds27-publication-artifact-map/v1', study_root=str(study),
        excludes=['raw IQ', 'full orbit banks/arrays', 'private exports', 'full per-case model arrays',
                  'redundant full ALGO03 job.result terminal envelopes'],
        deterministic_gzip_mtime=0, artifacts=records,
        publication_only_files_unmapped_to_study_source=True)
    (destination / 'artifact-map.json').write_bytes(json_bytes(artifact_map))
    if manifest:
        files = {str(p.relative_to(destination)): dict(sha256=sha(p.read_bytes()), bytes=p.stat().st_size)
                 for p in sorted(destination.rglob('*'))
                 if p.is_file() and p.name != 'publication-manifest.json'}
        document = dict(schema='ds27-publication-manifest/v1', files=files,
                        artifact_map_sha256=sha((destination / 'artifact-map.json').read_bytes()),
                        no_raw_IQ_or_full_orbit_arrays=True)
        (destination / 'publication-manifest.json').write_bytes(json_bytes(document))
    return dict(artifacts=len(records), published_bytes=sum(r['published_bytes'] for r in records),
                destination=str(destination), manifest_created=manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=STUDY)
    parser.add_argument('--destination', type=Path, default=DESTINATION)
    parser.add_argument('--include-failed-native', action='store_true')
    parser.add_argument('--manifest', action='store_true')
    args = parser.parse_args()
    print(json.dumps(bundle(args.study.resolve(), args.destination.resolve(),
        include_failed_native=args.include_failed_native, manifest=args.manifest)), flush=True)
