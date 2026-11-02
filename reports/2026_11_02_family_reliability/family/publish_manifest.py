"""Allowlist compact family artifacts and bind excluded dense evidence."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def item(p):
    return dict(path=str(p.relative_to(ROOT.parent)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)

def main():
    names=['README.md','prototype.py','run.py','summarize.py','verify.py','test_prototype.py','publish_manifest.py',
        'protocol.json','model-invariant-checks.json','candidate_fits.csv','summary.json','comparison.png','family-residuals.png','tests.txt']
    allow=[ROOT/n for n in names]
    excluded=[p for p in ROOT.rglob('*') if p.is_file() and p not in allow and p.name!='publication_manifest.json' and '__pycache__' not in p.parts]
    result=dict(scope='Prototype B fixed existing-family physical covariance sensitivity; no promotion',
        allowlist=[item(p) for p in allow],excluded_dense_files=[item(p) for p in sorted(excluded)],
        dense_evidence_local_only=True)
    (ROOT/'publication_manifest.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
