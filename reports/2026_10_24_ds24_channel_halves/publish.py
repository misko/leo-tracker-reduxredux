"""Package the bounded channel ablation without staging the main working tree."""
import gzip,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DEST=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022/reports/2026_10_24_ds24_channel_halves')


def sha(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert json.loads((ROOT/'audit.json').read_bytes())['passed']
    assert json.loads((ROOT/'execution.json').read_bytes())['all_terminal']
    DEST.mkdir(parents=True,exist_ok=True)
    paths=[ROOT/n for n in ('README.md','RESULTS.md','protocol.json','source_receipt.json','audit.json',
                            'summary.json','execution.json','all_channel_reference_verification.json')]
    paths+=list(ROOT.glob('*.py'))+list((ROOT/'tables').glob('*.csv'))+list((ROOT/'figures').glob('*.png'))
    compact=[];products={}
    for group in ('ch1_4','ch5_8'):
        root=ROOT/group
        paths += [root/n for n in ('sample.json','channels.json','execution.json','audit.json')]
        paths += list((root/'engine').glob('*.py'))
        for member in json.loads((root/'sample.json').read_bytes())['selected']:
            case=member['dataset_label'];record=dict(group=group,case=case)
            selected=dict(execution=root/case/'baseline_execution.json',input=root/case/'input_receipt.json',
                          preparation=root/case/'prepared.json',original=root/case/'algo02_result.json',
                          baseline=root/'family_cavity/position'/(case+'.json'))
            for name,path in selected.items():
                if path.exists():record[name]=json.loads(path.read_bytes())
            compact.append(record)
            for path in (root/case).glob('*.json'):products[str(path)]=sha(path)
        for path in (root/'family_cavity').rglob('*.json'):products[str(path)]=sha(path)
    for path in paths:
        target=DEST/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,target)
    raw=(json.dumps(compact,separators=(',',':'))+'\n').encode()
    compressed=gzip.compress(raw,compresslevel=6,mtime=0)
    assert gzip.decompress(compressed)==raw
    (DEST/'numerical_results.json.gz').write_bytes(compressed)
    (DEST/'bulk_products.json').write_text(json.dumps(products,indent=2)+'\n')
    seal=dict(numerical_results_decompressed_sha256='sha256:'+hashlib.sha256(raw).hexdigest(),
              files={str(p.relative_to(DEST)):sha(p) for p in sorted(DEST.rglob('*')) if p.is_file() and p.name!='publication.json'})
    (DEST/'publication.json').write_text(json.dumps(seal,indent=2)+'\n')
    for name,h in seal['files'].items():assert sha(DEST/name)==h
    print(json.dumps(dict(files=len(seal['files']),bulk_products=len(products),total_bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file()))))


if __name__=='__main__':main()
