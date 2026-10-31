"""Independent roster, owner-count and publication integrity checks."""
import csv
import gzip
import json
import math
from pathlib import Path
import re
from evaluate import STUDY,read,digest
from summarize import OUT

def validate():
    rows=list(csv.DictReader((OUT/'per-case.csv').open()));summary=read(OUT/'summary.json')
    protocol=read(STUDY/'protocol.json');cases={r['case'] for r in protocol['roster']}
    assert len(cases)==159
    for method,arms in summary['metrics'].items():
        for arm,m in arms.items():
            rr=[r for r in rows if r['method']==method and r['arm']==arm]
            assert len(rr)==159 and {r['case'] for r in rr}==cases
            valid=[r for r in rr if r['state']=='complete']
            assert len(valid)==148 and m['unavailable']==11
            assert sum(int(r['glrt_points']) for r in valid)==650404
            assert sum(int(r['associated']) for r in valid)==m['associated']
            for r in valid:
                baseline=read(STUDY/'baselines'/f"{r['case']}.json")
                old=baseline['owners'][arm]
                assert int(r['baseline_associated'])==len(old)
                if r['trial_path']:
                    fit=read(Path(r['trial_path'])/'target_0.json')['arms'][arm]
                    owners=fit['proposed_owners']
                    assert all(owners.get(k)==v for k,v in old.items())
                    assert set(owners)<=set(baseline['observation_ids'])
                    assert len(owners)==int(r['associated'])
                else:
                    assert int(r['associated'])==len(old)
                    assert r['error_m']==r['baseline_error_m']
            mean=sum(float(r['error_m']) for r in valid)/len(valid)
            assert math.isclose(mean,m['mean_error_m'],rel_tol=1e-12)
    for relative,m in read(OUT/'artifact-map.json').items():
        assert digest(OUT/relative)==m['published_sha256']
        assert digest(m['source'])==m['source_sha256']
    links=[target for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',(OUT/'README.md').read_text())
           if '://' not in target and not target.startswith('#')]
    for target in links:
        if target in ('validation.json','publication-manifest.json'):continue
        assert (OUT/target.split('#')[0]).exists(),target
    def reject_constant(token):raise ValueError('non-finite JSON constant: '+token)
    for f in OUT.rglob('*'):
        if not f.is_file():continue
        if f.suffix=='.json':json.loads(f.read_text(),parse_constant=reject_constant)
        elif f.name.endswith('.json.gz'):json.loads(gzip.decompress(f.read_bytes()),parse_constant=reject_constant)
    result=dict(verified=True,roster=159,usable=148,total_glrt=650404,methods=len(summary['metrics']),
        checks=['all cases retained','unavailable not zero-scored','native point counts',
                'old owner preservation','fallback unchanged','summary means','source and published hashes',
                'Markdown links','finite JSON'])
    (OUT/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    files={str(p.relative_to(OUT)):digest(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='publication-manifest.json'}
    (OUT/'publication-manifest.json').write_text(json.dumps(dict(files_sha256=files),indent=2)+'\n')
    for target in links:assert (OUT/target.split('#')[0]).exists(),target
    print(json.dumps(result,indent=2))

if __name__=='__main__':validate()
