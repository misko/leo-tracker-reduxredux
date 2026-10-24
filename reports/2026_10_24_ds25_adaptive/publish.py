"""Package explicit DS25 artifacts, never stage the shared working checkout."""
import gzip
import hashlib
import json
import shutil
from pathlib import Path

OUT=Path(__file__).resolve().parent
DEST=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022/reports/2026_10_24_ds25_adaptive')


def sha(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert json.loads((OUT/'execution.json').read_bytes())['all_terminal']
    assert json.loads((OUT/'audit.json').read_bytes())['passed']
    paths=[OUT/n for n in ('README.md','RESULTS.md','sample.json','protocol.json','source_receipt.json',
        'execution.json','audit.json','summary.json','prior_fast_input_overlap.json',
        'mint.py','test_mint.py','report.py','test_report.py','audit.py','publish.py')]
    paths += list((OUT/'engine').glob('*.py'))+list((OUT/'figures').glob('*.png'))+list((OUT/'tables').glob('*.csv'))
    paths += [OUT/'dataset'/n for n in ('manifest.json.gz','manifest.sha256','verification.json','creation_receipt.json')]
    DEST.mkdir(parents=True,exist_ok=True)
    for path in paths:
        target=DEST/path.relative_to(OUT);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    compact=(OUT/'compact_results.json').read_bytes()
    (DEST/'compact_results.json.gz').write_bytes(gzip.compress(compact,compresslevel=6,mtime=0))
    assert gzip.decompress((DEST/'compact_results.json.gz').read_bytes())==compact
    previous=DEST/'compact_results.json'
    if previous.exists():
        assert previous.read_bytes()==compact
        previous.unlink()
    raw=gzip.decompress((DEST/'dataset/manifest.json.gz').read_bytes())
    assert 'sha256:'+hashlib.sha256(raw).hexdigest()==(DEST/'dataset/manifest.sha256').read_text().split()[0]
    dataset=json.loads(raw)
    listing=dict(dataset_id='DS25',parent_dataset='DS24 revision 2',counts=dataset['counts'],
                 members=[{k:m[k] for k in ('dataset_label','parent_dataset_label','recording_id',
                            'captured_utc_ns','recording_state','window_count','sample_rate_hz')}
                          for m in dataset['members']])
    (DEST/'dataset/membership-summary.json').write_text(json.dumps(listing,indent=2)+'\n')
    products={}
    for directory in sorted(OUT.glob('DS*')):
        if directory.is_dir():
            for path in directory.glob('*.json'):
                products[str(path)]=sha(path)
    for directory in (OUT/'family_cavity',OUT/'family_cavity/position'):
        for path in directory.glob('*.json'):products[str(path)]=sha(path)
    (DEST/'bulk_products.json').write_text(json.dumps(products,indent=2)+'\n')
    seal=dict(dataset_decompressed_manifest_sha256='sha256:'+hashlib.sha256(raw).hexdigest(),
              files={str(p.relative_to(DEST)):sha(p) for p in sorted(DEST.rglob('*'))
                     if p.is_file() and p.name!='publication.json'})
    (DEST/'publication.json').write_text(json.dumps(seal,indent=2)+'\n')
    for name,h in seal['files'].items():assert sha(DEST/name)==h
    print(json.dumps(dict(published_files=len(seal['files']),bulk_products=len(products),
                         total_bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()))))


if __name__=='__main__':main()
