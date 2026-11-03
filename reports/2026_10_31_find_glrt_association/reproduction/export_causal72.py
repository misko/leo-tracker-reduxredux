"""Export a general 72-hour causal catalogue, independent of RF candidates."""
import argparse
import json
from pathlib import Path
from sgp4.exporter import export_tle
from leo.operations.tle_archive import TleArchiveReader
from leo.operations.causal_tle_catalogue import causal_catalogue


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();out={}
    reader=TleArchiveReader(Path('/var/lib/leo/tle'))
    for case in sorted({r['case'] for r in json.loads((a.output/'targets.json').read_text())}):
        receipt=json.loads((a.output/'cases'/case/'receipt.json').read_text())['scan_receipt']
        cat=causal_catalogue(reader,receipt['cutoff_utc_ns'],maximum_age_s=72*3600.)
        out[case]=dict(snapshot_count=cat.snapshot_count,elements={str(n):dict(prov,lines=list(export_tle(sat))) for n,sat,prov in zip(cat.catalogue.satellite_numbers,cat.catalogue.satellites,cat.provenance)})
    print(json.dumps(dict(policy='complete STARLINK catalogue, 72-hour element and archive window, both epoch and collection <= causal cutoff; no RF selection',scans=out),allow_nan=False))
