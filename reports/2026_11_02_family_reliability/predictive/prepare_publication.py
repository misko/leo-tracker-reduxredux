"""Lean report publication inventory; raw numerical artifacts stay local."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parent
REPORT=ROOT.parent


def read(path):return json.loads(path.read_text())


def write(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def entry(path):
    return dict(path=path.relative_to(REPORT).as_posix(),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size)


def compact():
    keys=('case','arm','fold','norad','SD_scale','solver','x_km','reference','position_covariance_km2',
        'position_precision_eigenvalues','position_curvature_floored','phase_closed','phase_change_s','boundary',
        'optimizer_success','evaluations','train_points','held_points','train_ids_sha256','held_ids_sha256',
        'numerical_fit_qualified','unqualified_reasons','original_numerical_fit_qualified','original_unqualified_reasons',
        'unseen_noise_group_held_points','cap15_minus_cap8_negative_twice_log_density','covariance_audit',
        'reconstructed_unbounded_score_deltas')
    collections={}
    for stage,paths in [('cap8',[ROOT/(c+'_results.json')for c in ['DS26-0309','DS26-0070']]),
                        ('cap15',[ROOT/'extended/results.json']),('bounded',[ROOT/'bounded/results.json'])]:
        out=[]
        for path in paths:
            obj=read(path)
            for r in obj['rows']:
                rr=dict(r);rr.setdefault('case',obj.get('case'))
                small={k:rr[k]for k in keys if k in rr}
                if 'error'in rr:small['error']=rr['error']
                if 'scores'in rr:
                    scores={}
                    for subset in ['all','target','other']:
                        s=rr['scores'][subset]
                        if stage=='bounded':
                            ss={k:v for k,v in s.items()if k not in ('prior_box','posterior_box')}
                            ss['prior_box_log_probability']=s['prior_box']['log_probability']
                            ss['posterior_box_log_probability']=s['posterior_box']['log_probability']
                            scores[subset]=ss
                        else:scores[subset]=s
                    small['scores']=scores
                small['raw_source']=path.relative_to(REPORT).as_posix()
                out.append(small)
        collections[stage]=out
    target=ROOT/'cell_summaries.json'
    target.write_text(json.dumps(dict(scope='Compact endpoints, covariance and marginal scores; complete per-family scores are in CSV; full traces remain local with hashes in retained_artifacts.json',**collections),separators=(',',':'),allow_nan=False)+'\n')


def allowed(path):
    if '__pycache__'in path.parts or '.pytest_cache'in path.parts:return False
    if path.name in ('publication_manifest.json','retained_artifacts.json'):return False
    if path.suffix in ('.py','.md','.csv','.png','.sha256'):return True
    return path.suffix=='.json'and(path.name in ('run_manifest.json','protocol.json','audit_summary.json','cell_summaries.json')
        or path.name.endswith(('_protocol.json','_inventory.json')))


def check_links(paths):
    published={p.resolve()for p in paths}
    for path in paths:
        if path.suffix!='.md':continue
        for dest in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target=dest.strip().split()[0].strip('<>')
            if re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target)or target.startswith('#'):continue
            local=(path.parent/unquote(target.split('#')[0])).resolve()
            if local in published:continue
            if local.is_file()and not local.is_relative_to(REPORT):continue
            raise ValueError(f'Unpublished or missing Markdown target: {path}: {target}')


def main():
    compact()
    files=sorted(p for p in ROOT.rglob('*')if p.is_file())
    selected=[p for p in files if allowed(p)]
    retained=[]
    for path in files:
        if path in selected or path.name in ('publication_manifest.json','retained_artifacts.json'):continue
        if '__pycache__'in path.parts or '.pytest_cache'in path.parts:continue
        retained.append(dict(entry(path),reason='Full raw/duplicate numerical result or execution log retained locally; compact summaries and score CSVs are published.'))
    write(ROOT/'retained_artifacts.json',dict(retained=retained,
        path_base='2026_11_02_family_reliability report root; retained paths intentionally absent from publication',
        ignored_generated_patterns=['**/__pycache__/**','**/.pytest_cache/**']))
    selected.append(ROOT/'retained_artifacts.json');selected.sort()
    check_links(selected)
    write(ROOT/'publication_manifest.json',dict(allowlist=[entry(p)for p in selected]))
    print(json.dumps(dict(allowlisted_files=len(selected),allowlisted_bytes=sum(p.stat().st_size for p in selected),retained_files=len(retained),retained_bytes=sum(r['bytes']for r in retained))))


if __name__=='__main__':main()
