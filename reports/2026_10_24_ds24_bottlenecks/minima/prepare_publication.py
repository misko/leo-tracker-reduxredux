"""Copy final research evidence and seal publication provenance; no inference."""
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

RESEARCH=Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024')
PUBLISHER=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
DEST=PUBLISHER/'reports/2026_10_24_ds24_bottlenecks'
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
FULL=Path('/srv/bulk/leo/research/ds25-20261024')
HALF=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')


def read(path):return json.loads(path.read_text())
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def record(path):return dict(path=str(path),bytes=path.stat().st_size,sha256=digest(path))
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2)+'\n')


def main():
    assert (RESEARCH/'README.md').exists() and (RESEARCH/'evidence/FINDINGS.md').exists()
    DEST.mkdir(parents=True,exist_ok=True)
    if (DEST/'source/repository').exists():shutil.rmtree(DEST/'source/repository')
    direct=[];raw=[]
    for path in sorted(RESEARCH.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(RESEARCH)
        if 'mpl' in rel.parts or '__pycache__' in rel.parts or path.name.endswith('.partial.json') or path.name=='publication.log':continue
        if path.suffix not in ('.md','.py','.json','.csv','.png','.log','.txt'):continue
        bulky=(path.suffix=='.json' and (path.name.startswith('DS24-') or path.name in ('all_cases.json','residuals.json')))
        bulky=bulky or path.name in ('curved_point_residuals.csv','track_residual_metrics.csv')
        if rel.parts[0]=='objective':bulky=False
        (raw if bulky else direct).append((path,rel))
    copied=[]
    for path,rel in direct:
        target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        copied.append(dict(source=str(path),published=str(rel),bytes=path.stat().st_size,sha256=digest(path)))
    # Deterministic archive metadata; preserve bytes and logical relative paths.
    archive=DEST/'raw_results.tar.gz';members=[]
    with archive.open('wb') as output,gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
        for path,rel in raw:
            payload=path.read_bytes();entry=tarfile.TarInfo(str(rel));entry.size=len(payload);entry.mode=0o644;entry.mtime=0
            tar.addfile(entry,io.BytesIO(payload));members.append(dict(source=str(path),member=str(rel),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    # Resolve static local imports and preserve exact runtime source bytes.
    roots=[REPO/'tools',REPO/'src',FULL/'engine']+[p for p in RESEARCH.rglob('*') if p.is_dir() and 'mpl' not in p.parts]
    sources={p for p,_ in direct if p.suffix=='.py'}
    queue=list(sources)
    while queue:
        path=queue.pop()
        try:tree=ast.parse(path.read_text())
        except (UnicodeDecodeError,SyntaxError):continue
        modules=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):modules.extend(a.name for a in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module:
                modules.append(node.module);modules.extend(node.module+'.'+a.name for a in node.names)
        for module in modules:
            relative=Path(*module.split('.'))
            for root in roots:
                candidates=[root/relative.with_suffix('.py'),root/relative/'__init__.py']
                found=next((p for p in candidates if p.is_file()),None)
                if found:
                    if found not in sources:sources.add(found);queue.append(found)
                    break
    extras=[REPO/'src/leo/analysis/starlink/fast_scan_scores.py',REPO/'native/adaptive/detector/kernel/private/full_search.c',
        REPO/'native/adaptive/detector/kernel/private/native_presence/presence.c',
        REPO/'docs/operations/radio20-lt3d-004b-20261001.md',REPO/'deploy/station/gauss-r20-lt3d-004b-20261001-v1.json',HALF/'report.py']
    sources.update(extras)
    relevant={'algo02_scan.py','ds24_engine.py','evaluate_ds23_phase_refreshed.py','probe_ds23_frequency_events.py',
        'probe_ds23_family_cavity_position.py','probe_ds23_family_cavity_nominations.py','probe_ds23_graph_seeded_paths.py',
        'ds23_frequency_events.py','ds23_family_cavity.py','investigate_dsx01_localization_failures.py',
        'continuous_curve_fit.py','dsx01_joint_marginal.py','ds23_position_information.py','ds23_predictive_linear.py',
        'build_dsx01_orbit_modes.py','ds23_height_problem.py','ds23_radio_noise.py','debug_algo02_ds23_0268.py',
        'probe_ds23_gate_retention_cohort.py','ds23_feasible_position.py','fast_scan_native.py'}
    source_records=[]
    for path in sorted(sources):
        if path.is_relative_to(RESEARCH):published=path.relative_to(RESEARCH)
        elif path.is_relative_to(REPO):published=Path('source/repository')/path.relative_to(REPO)
        elif path.is_relative_to(FULL/'engine'):published=Path('source/engine')/path.name
        else:published=Path('source/original_channel_halves_report.py')
        snapshot=path.is_relative_to(RESEARCH) or path in extras or path.name in relevant
        if snapshot:
            target=DEST/published;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        source_records.append(dict(source=str(path),published=str(published) if snapshot else None,
            snapshotted=snapshot,bytes=path.stat().st_size,sha256=digest(path)))
    write(DEST/'source_manifest.json',dict(scope='all static local imports hashed; new analysis/relevant numerical modules, native CFO scorer and station authority snapshotted; remaining unchanged helper dependencies use the existing repository and prior full/half source seals',files=source_records))
    # Pin all persisted scan artifacts and causal receipts for the 24-case cohort.
    cases=read(HALF/'summary.json')['baseline']['c0']['common_cases'];inputs=set()
    for root in (FULL,HALF/'ch1_4',HALF/'ch5_8'):
        for case in cases:
            inputs.update(p for p in (root/case).glob('*') if p.is_file() and p.suffix in ('.json','.npz','.tle'))
            inputs.add(root/'family_cavity/position'/(case+'.json'))
            for location in (root/'causal_prior'/case,root/'causal_phase_history'):
                if location.exists():inputs.update(p for p in location.glob('*') if p.is_file() and (location.name==case or p.name.startswith(case)))
        for name in ('sample.json','summary.json','protocol.json','source_receipt.json'):
            if (root/name).exists():inputs.add(root/name)
    inputs.update([HALF/'all_channel_reference_verification.json',HALF/'tables/positions.csv',HALF/'tables/paired_errors.csv'])
    tracking=read(FULL/'DS24-0101/tracking.json');source=tracking['source'];run=tracking['provenance']['run_id']
    native_manifest=Path('/srv/bulk/leo/analysis')/source['session_id']/run/'manifest.json'
    inputs.add(native_manifest)
    native=read(native_manifest)
    native_products=0
    for product in native['products']:
        if product['kind']!='fast-scan.glrt':continue
        path=Path('/srv/bulk/leo')/product['logical_uri'].removeprefix('bulk://')
        assert 'sha256:'+digest(path)==product['digest'];inputs.add(path);native_products+=1
    raw_path=Path(read(RESEARCH/'evidence/acquisition_provenance.json')['raw_manifest_path'])
    member=next(r for r in read(FULL/'sample.json')['selected'] if r['dataset_label']=='DS24-0101')
    raw_receipt=next(r for r in member['raw_manifest_receipts'] if r['path']==str(raw_path))
    input_records=[record(p) for p in sorted(inputs)]
    write(DEST/'input_manifest.json',dict(scope='persisted full/half scan artifacts, causal receipts, cohort tables and representative sealed native GLRT products; no raw IQ',files=input_records,
        raw_manifest_prior_receipt=dict(**raw_receipt,independently_rehashed_for_publication=False,
            reason='raw recording directory denies read access; prior frozen sample receipt retained; acquisition metadata report is the already-completed audit')))
    # Independently replay the published-result hash authority and read audit invariants.
    authority=read(HALF/'all_channel_reference_verification.json');verified=[]
    assert authority['passed'] and len(authority['verified_results'])==48
    for row in authority['verified_results']:
        path=Path(row['path']);actual='sha256:'+digest(path);assert actual==row['sha256']
        verified.append(dict(path=str(path),expected_sha256=row['sha256'],actual_sha256=actual,unchanged=True))
    objective=[read(p) for p in sorted((RESEARCH/'objective').glob('DS24-*.json'))]
    assert len(objective)==24
    changes=[];replay=[];decomposition=[]
    for case in objective:
        assert set(case['arms'])=={'c0','fitted_c'}
        for arm,r in case['arms'].items():
            changes.append(r['evaluation_site']['phase_changes_s'][-1]);replay.append(abs(r['replay_difference']))
            for location in ('endpoint','evaluation_site'):
                x=r[location]['decomposition'];decomposition.append(abs(x['reconstruction_error']))
                assert abs(sum(x['terms'].values())-r[location]['loss'])<1e-6
    assert max(changes)<1e-5 and max(replay)<1e-3 and max(decomposition)<1e-6
    count=read(RESEARCH/'evidence/likelihood_count_audit.json');assert count['all_assertions_passed'] and len(count['rows'])==144
    expected={'all_channels':(78067,108600),'ch1_4':(42621,60059),'ch5_8':(33339,48541)}
    for group,(points,total) in expected.items():
        for arm in ('c0','fitted_c'):
            rr=[r for r in count['rows'] if r['group']==group and r['arm']==arm]
            assert sum(r['likelihood_union_ids'] for r in rr)==points and sum(r['GLRT'] for r in rr)==total
    information=read(RESEARCH/'information/audit.json');assert information['all48_replay_passed']
    minima=read(RESEARCH/'minima/summary.json');assert minima['fixed_arm_fits']==30 and minima['adopted_fixed_cases']==0 and minima['adopted_transfer_cases']==0
    # Archive bytes, direct copy bytes and source bytes must all match their authorities.
    with tarfile.open(archive,'r:gz') as tar:
        for item in members:assert hashlib.sha256(tar.extractfile(item['member']).read()).hexdigest()==item['sha256']
    for item in copied+source_records:
        if item['published'] is not None:assert digest(DEST/item['published'])==item['sha256']
    write(DEST/'archive_manifest.json',dict(archive=dict(path=archive.name,bytes=archive.stat().st_size,sha256=digest(archive)),members=members,direct_copies=copied,
        source_manifest=dict(path='source_manifest.json',sha256=digest(DEST/'source_manifest.json')),
        input_manifest=dict(path='input_manifest.json',sha256=digest(DEST/'input_manifest.json'))))
    audit=dict(passed=True,no_new_RF_or_policy_adoption=True,diagnostics_are_descriptive_not_randomized_holdout_validation=True,
        original_full_results=dict(count=48,all_unchanged=True,authority=str(HALF/'all_channel_reference_verification.json'),verified=verified),
        fixed_site=dict(cases=24,arms=48,max_absolute_replay_difference=max(replay),max_final_phase_change_s=max(changes),max_decomposition_reconstruction_error=max(decomposition),all_decompositions_close=True),
        corrected_counts=dict(records=144,all_assertions_passed=True,totals={k:dict(likelihood_points=v[0],GLRT_points=v[1],percent=100*v[0]/v[1]) for k,v in expected.items()}),
        information=information,minima=minima,native_products_hash_verified=native_products,
        copied_files=len(copied),archived_files=len(members),source_files=len(source_records),
        source_snapshots=sum(r['snapshotted'] for r in source_records),input_files=len(input_records),
        archive_manifest_sha256=digest(DEST/'archive_manifest.json'))
    write(DEST/'audit.json',audit)
    print(json.dumps({k:v for k,v in audit.items() if k in ('passed','fixed_site','copied_files','archived_files','source_files','input_files')},indent=2))


if __name__=='__main__':main()
