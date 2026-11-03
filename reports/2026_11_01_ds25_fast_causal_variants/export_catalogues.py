"""Archive-adapter export; causal only, general catalogue, no RF filtering."""
from functools import lru_cache
from sgp4.exporter import export_tle
from leo.operations.tle_archive import TleArchiveReader
import leo.operations.causal_tle_catalogue as causal
from common import ROOT,read,write
from pathlib import Path

original=causal.parse_element_sets
causal.parse_element_sets=lru_cache(maxsize=64)(original)
reader=TleArchiveReader(Path('/var/lib/leo/tle'))
for z in sorted(read(ROOT/'protocol.json')['cohort'],key=lambda r:r['cutoff_utc_ns']):
    out=ROOT/'catalogues'/(z['case']+'.json')
    if out.exists():continue
    c=causal.causal_catalogue(reader,z['cutoff_utc_ns'],maximum_age_s=72*3600)
    write(out,dict(case=z['case'],cutoff_utc_ns=z['cutoff_utc_ns'],snapshot_count=c.snapshot_count,
        elements={str(n):dict(p,lines=list(export_tle(s))) for n,s,p in zip(c.catalogue.satellite_numbers,c.catalogue.satellites,c.provenance)}))
    print(z['case'],len(c.provenance),flush=True)
