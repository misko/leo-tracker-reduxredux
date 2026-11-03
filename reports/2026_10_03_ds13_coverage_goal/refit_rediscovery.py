"""Unchanged full-bank training discovery after expanded calibration refit.

Each RF arm uses its own refitted selected-catalog timing mean as the common
search center. Results remain training proposals, not new coverage evidence.
"""
import argparse,json,sys
from benchmark import ROOT,digest
import adaptive_discovery


def calibration_input(refit,arm):
    fit=refit['arms'][arm]
    if not fit['catalog_numbers']:raise ValueError('No fitted catalogs')
    return dict(catalog_numbers=fit['catalog_numbers'],arms={arm:dict(parameters=fit['parameters'],
        rf_coefficient_hz_per_ghz=fit['coefficient'],attempts=fit['attempts'])},
        original_train_rows=refit['original_train_rows'],original_test_rows=refit['original_test_rows'],
        scope='Adapter for training-only refitted nuisance parameters; no test observations are used for discovery.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--scan',choices=['A','B'],required=True);p.add_argument('--arm',choices=['fitted-c','zero-c'],required=True);args=p.parse_args()
    source=ROOT/'expanded-training-refit/fold-0'/f'{args.scan}.json';refit=json.loads(source.read_text())
    union=ROOT/'training-union/fold-0'/f'{args.scan}.json'
    if refit['source_sha256']!=digest(union):raise ValueError('Refit source changed')
    namespace=ROOT/'refit-rediscovery'/args.arm;namespace.mkdir(parents=True,exist_ok=True)
    frozen=namespace/'frozen'
    if not frozen.exists():
        try:frozen.symlink_to(ROOT/'frozen',target_is_directory=True)
        except FileExistsError:pass
    if frozen.resolve()!=(ROOT/'frozen').resolve():raise ValueError('Unexpected frozen data')
    receipt=calibration_input(refit,args.arm);receipt['sources']={str(p):digest(p) for p in (source,union,ROOT/'adaptive_discovery.py',ROOT/'refit_rediscovery.py')}
    target=namespace/'training-calibration/fold-0'/f'{args.scan}.json';target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x') as f:json.dump(receipt,f,indent=2)
    oldroot=adaptive_discovery.ROOT;oldargv=sys.argv
    try:
        adaptive_discovery.ROOT=namespace;sys.argv=['adaptive_discovery.py','--scan',args.scan,'--fold','0','--arm',args.arm]
        adaptive_discovery.main()
    finally:adaptive_discovery.ROOT=oldroot;sys.argv=oldargv


if __name__=='__main__':main()
