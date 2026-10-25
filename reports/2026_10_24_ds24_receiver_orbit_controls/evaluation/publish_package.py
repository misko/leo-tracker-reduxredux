"""Package sealed DS24 controls without fitting or changing prior reports."""
import ast
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import tarfile
from urllib.parse import unquote

ROOT=Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
PUB=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
DEST=PUB/'reports/2026_10_24_ds24_receiver_orbit_controls'
PRIOR=PUB/'reports/2026_10_24_ds24_bottlenecks'
REPO=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
FULL=Path('/srv/bulk/leo/research/ds25-20261024')
HALF=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')


def read(p):return json.loads(p.read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def meta(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)


def main():
    DEST.mkdir(parents=True,exist_ok=True)
    raw=[];direct=[]
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if 'mpl' in rel.parts or '__pycache__' in rel.parts or p.name=='publication.log':continue
        if p.suffix not in ('.md','.py','.json','.csv','.png','.log','.txt'):continue
        bulky=p.suffix=='.json' and (p.name.startswith('DS24-') or rel in (Path('orbit/projected_rows.json'),Path('orbit/validation.json')))
        (raw if bulky else direct).append((p,rel))
    copies=[]
    for p,rel in direct:
        target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        copies.append(dict(source=str(p),published=str(rel),sha256=sha(p),bytes=p.stat().st_size))
    archive=DEST/'raw_results.tar.gz';members=[]
    with archive.open('wb') as output,gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
        for p,rel in raw:
            payload=p.read_bytes();entry=tarfile.TarInfo(str(rel));entry.size=len(payload);entry.mode=0o644;entry.mtime=0
            tar.addfile(entry,io.BytesIO(payload));members.append(dict(source=str(p),member=str(rel),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest()))
    # Hash all local dependencies; snapshot the new/relevant numerical modules.
    sources={p for p,_ in direct if p.suffix=='.py'};queue=list(sources)
    roots=[REPO/'tools',REPO/'src']+[p for p in ROOT.rglob('*') if p.is_dir() and 'mpl' not in p.parts]
    while queue:
        p=queue.pop()
        try:tree=ast.parse(p.read_text())
        except (UnicodeDecodeError,SyntaxError):continue
        modules=[]
        for n in ast.walk(tree):
            if isinstance(n,ast.Import):modules.extend(a.name for a in n.names)
            elif isinstance(n,ast.ImportFrom) and n.module:modules.append(n.module);modules.extend(n.module+'.'+a.name for a in n.names)
        for module in modules:
            relative=Path(*module.split('.'))
            found=next((p for root in roots for p in (root/relative.with_suffix('.py'),root/relative/'__init__.py') if p.is_file()),None)
            if found is not None and found not in sources:sources.add(found);queue.append(found)
    relevant={Path(r['source']).name for r in read(PRIOR/'source_manifest.json')['files'] if r.get('snapshotted') and Path(r['source']).is_relative_to(REPO)}
    relevant.update(['ds23_correlated_orbit_problem.py','prototype_dsx01_glrt_weighting.py','retained_track_likelihood.py',
        'polynomial_satellite_diagnostics.py','compare_dsx01_frame_joint.py','orbit_uncertainty.py','orbit_phase_geometry.py'])
    source_records=[]
    for p in sorted(sources):
        snapshot=p.is_relative_to(ROOT) or p.name in relevant
        rel=p.relative_to(ROOT) if p.is_relative_to(ROOT) else Path('source/repository')/p.relative_to(REPO)
        if snapshot:
            target=DEST/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        source_records.append(dict(source=str(p),published=str(rel) if snapshot else None,snapshotted=snapshot,sha256=sha(p),bytes=p.stat().st_size))
    write(DEST/'source_manifest.json',dict(scope='New analysis scripts plus exact relevant runtime snapshots; complete static local import closure hashed, unchanged helpers also bound by prior source seal',prior_source_manifest=dict(path='../2026_10_24_ds24_bottlenecks/source_manifest.json',sha256=sha(PRIOR/'source_manifest.json')),files=source_records))
    # Reuse the previous complete input inventory while independently rehashing
    # every full-cohort persisted artifact and causal receipt used in this study.
    inputs=[]
    for item in read(PRIOR/'input_manifest.json')['files']:
        p=Path(item['path'])
        if p.is_relative_to(FULL) or p in (HALF/'summary.json',HALF/'tables/positions.csv',HALF/'tables/paired_errors.csv',HALF/'all_channel_reference_verification.json'):
            assert sha(p)==item['sha256'];inputs.append(meta(p))
    write(DEST/'input_manifest.json',dict(scope='Full DS24 persisted scan artifacts and causal histories independently rehashed against previous input seal; frozen cohort/count artifacts retained',prior_input_manifest=dict(path='../2026_10_24_ds24_bottlenecks/input_manifest.json',sha256=sha(PRIOR/'input_manifest.json')),files=inputs,
        count_audit=dict(path='likelihood_count_audit.csv',sha256=sha(ROOT/'likelihood_count_audit.csv'))))
    original=read(HALF/'all_channel_reference_verification.json');assert original['passed'] and len(original['verified_results'])==48
    for item in original['verified_results']:assert 'sha256:'+sha(Path(item['path']))==item['sha256']
    seal=read(ROOT/'evaluation/batch_seal.json');assert seal['passed'] and seal['total_arm_results']==144 and seal['total_paired_cases']==72
    audits=[]
    for model in seal['models']:
        for item in model['results']:assert sha(Path(item['path']))==item['sha256']
        for key in ('protocol','execution','replay_audit'):
            p=Path(model['protocol_path']) if key=='protocol' else ROOT/'evaluation/models'/model['model_id']/('execution.json' if key=='execution' else 'independent_replay_audit.json')
            assert sha(p)==model[key+'_sha256']
        audit=read(ROOT/'evaluation/models'/model['model_id']/'independent_replay_audit.json')
        assert audit['passed'] and audit['replayed_arms']==48;audits.append(audit)
    tests=[]
    for relative,count in [('noise/tests.txt',3),('receiver/tests.log',7),('orbit/test.log',3),('evaluation/tests.log',4),('evaluation/fallback_tests.log',2)]:
        p=ROOT/relative;text=p.read_text()
        assert (re.search(r'Ran '+str(count)+r' tests',text) and '\nOK' in text) or re.search(str(count)+r' passed',text)
        tests.append(dict(path=relative,count=count,sha256=sha(p),passed=True))
    assert sum(r['count'] for r in tests)==19
    geo=read(ROOT/'orbit/geographic_report_review.json');assert geo['passed'] and geo['published_position_rows']==336 and geo['summary_rows']==14
    for path,digest in geo['sha256'].items():assert sha(Path(path))==digest
    adapter=read(ROOT/'receiver/final_adapter_audit.json');assert adapter['passed'] and adapter['records_checked']==96
    orbit=read(ROOT/'orbit/audit.json');assert orbit['all_randomized_group_fits_passed_causal_and_endpoint_audit']
    assert read(ROOT/'orbit/eligibility.json')['qualified'] is False
    for path,digest in orbit['sha256'].items():assert sha(Path(path))==digest
    links=[]
    for p in DEST.rglob('*.md'):
        if 'source' in p.relative_to(DEST).parts:continue
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            if target.startswith(('http:','https:','mailto:','#')):continue
            local=unquote(target.strip('<>').split('#')[0])
            if local:assert (p.parent/local).exists(),(p,target);links.append(dict(document=str(p.relative_to(DEST)),target=target))
    from PIL import Image
    figures=[]
    for p in DEST.rglob('*.png'):
        with Image.open(p) as im:im.verify()
        figures.append(str(p.relative_to(DEST)))
    assert len(figures)==6
    with tarfile.open(archive,'r:gz') as tar:
        for item in members:assert hashlib.sha256(tar.extractfile(item['member']).read()).hexdigest()==item['sha256']
    for item in copies+source_records:
        if item.get('published') is not None:assert sha(DEST/item['published'])==item['sha256']
    write(DEST/'archive_manifest.json',dict(archive=dict(path=archive.name,sha256=sha(archive),bytes=archive.stat().st_size),members=members,direct_copies=copies,
        source_manifest_sha256=sha(DEST/'source_manifest.json'),input_manifest_sha256=sha(DEST/'input_manifest.json')))
    audit=dict(passed=True,original_published_full_result_hashes_unchanged=48,original_full_result_authority_sha256=sha(HALF/'all_channel_reference_verification.json'),
        paired_cases=72,new_arm_fits=144,all_endpoint_replays_passed=True,max_objective_replay_difference=max(a['maximum_absolute_objective_replay_difference'] for a in audits),
        max_RMS_replay_difference_hz=max(a['maximum_absolute_RMS_replay_difference_hz'] for a in audits),max_decomposition_error=max(a['maximum_absolute_decomposition_error'] for a in audits),
        original_physical_bindings_and_predictive_calibration_separation_preserved=True,tests=tests,total_tests=19,
        construction_checks=96,construction_maximum_loading_error_hz=adapter['maximum_loading_error_hz'],
        geographic_report_review=dict(passed=True,position_rows=336,summary_rows=14,sha256=sha(ROOT/'orbit/geographic_report_review.json')),
        orbit_qualification_failed_no_position_fits=True,no_new_RF_or_production_algorithm_release=True,
        local_links_checked=len(links),missing_links=0,figures=figures,
        copied_files=len(copies),raw_archive_members=len(members),source_dependencies_hashed=len(source_records),source_snapshots=sum(r['snapshotted'] for r in source_records),inputs_rehashed=len(inputs),
        archive_manifest_sha256=sha(DEST/'archive_manifest.json'))
    write(DEST/'audit.json',audit)
    print(json.dumps({k:v for k,v in audit.items() if k not in ('tests','geographic_report_review')},indent=2))


if __name__=='__main__':main()
