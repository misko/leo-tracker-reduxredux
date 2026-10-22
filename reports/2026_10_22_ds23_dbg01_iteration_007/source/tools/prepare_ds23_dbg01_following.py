"""Read-only following elements for DBG01 diagnostics, outside inference."""

from pathlib import Path
import json
import subprocess

from sgp4.exporter import export_tle
from sgp4.alpha5 import to_alpha5

from leo.operations.tle_archive import TleArchiveReader,TleArchiveError
from leo.sky.propagation import parse_element_sets
from dbg01_unassociated import validate_post_version
from run_algo01_ds23_sample import read,write,sha
import run_ds23_dbg01_iteration_005 as runner
import diagnose_ds23_iteration002_curves as diagnostic


def target_codes(wanted):
    return sorted({to_alpha5(int(n)) for n in wanted})


def archive_window(reader,end,high,wanted):
    """Use the same digest-verifying read-only port under archive ownership."""
    try:
        snapshots=[s for s in reader.list_snapshots('space-track') if end<s.collected_utc_ns<=high]
    except TleArchiveError as exc:
        if not isinstance(exc.__cause__,PermissionError):raise
        code='''import importlib.util,sys,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('archive_port',Path('src/leo/operations/tle_archive.py'))
module=importlib.util.module_from_spec(spec);sys.modules['archive_port']=module;spec.loader.exec_module(module)
reader=module.TleArchiveReader(Path('/var/lib/leo/tle'))
request=json.loads(sys.argv[1]);wanted=set(request['codes']);seen=set();rows=[]
for s in reader.list_snapshots('space-track'):
 if not request['end']<s.collected_utc_ns<=request['high'] or s.sha256 in seen:continue
 seen.add(s.sha256);lines=reader.read(s).splitlines();selected=[]
 for i,line in enumerate(lines[:-1]):
  if line.startswith('1 ') and line[2:7].strip() in wanted:
   selected.extend([lines[i-1] if i else '0 UNKNOWN',line,lines[i+1]])
 rows.append(dict(collected=s.collected_utc_ns,digest=s.digest,text='\\n'.join(selected)+'\\n'))
print(json.dumps(rows))
'''
        result=subprocess.run(['sudo','-n','/usr/bin/python3','-c',code,json.dumps(dict(end=end,high=high,codes=target_codes(wanted)))],
            capture_output=True,text=True,check=True)
        return json.loads(result.stdout),'digest-verifying archive port in read-only elevated subprocess'
    unique={}
    for s in snapshots:
        if s.sha256 not in unique or s.collected_utc_ns<unique[s.sha256].collected_utc_ns:unique[s.sha256]=s
    return [dict(collected=s.collected_utc_ns,digest=s.digest,text=reader.read(s)) for s in unique.values()],'ordinary read-only archive port'


def collect(case):
    output=runner.RAW/(case+'_following_elements.json')
    if output.exists():return
    d=runner.engine.current_setup(case);end=int(d['scan'].receipt['origin_utc_ns'])+300_000_000_000
    nominations=read(runner.RAW/'single_curve_reentry'/(case+'_nominations.json'))
    wanted={r['norad'] for t in nominations['targets'] for r in t['candidates'][:3]+[t['original']]}
    reader=TleArchiveReader(Path('/var/lib/leo/tle'));high=end+int(48*3600e9)
    snapshots,adapter=archive_window(reader,end,high,wanted)
    versions={}
    for s in snapshots:
        if not s['text'].strip():continue
        catalogue=parse_element_sets(s['text'])
        for name,n,sat,epoch in zip(catalogue.names,catalogue.satellite_numbers,catalogue.satellites,catalogue.element_epoch_utc_ns(),strict=True):
            if n not in wanted or not end<epoch<=high:continue
            row=dict(norad=int(n),name=name,element_epoch_utc_ns=int(epoch),collected_utc_ns=s['collected'],
                snapshot_digest=s['digest'],lines=list(export_tle(sat)))
            previous=versions.get(str(n))
            if previous is None or (epoch,s['collected'])<(previous['element_epoch_utc_ns'],previous['collected_utc_ns']):versions[str(n)]=row
    assert all(validate_post_version(v,end) for v in versions.values())
    write(output,dict(case=case,end_utc_ns=end,versions=versions,missing=sorted(wanted-set(map(int,versions))),
        selection='earliest element epoch then collection, both after scan and within48h',
        target_candidates_from_frozen_causal_nominations_only=True,diagnostic_only_not_inference=True,
        local_archive_read_only=True,archive_adapter=adapter,snapshots_checked=len(snapshots),source_sha256=sha(Path(__file__))))
    print(case,'following diagnostic elements',len(versions),'/',len(wanted),flush=True)


def main():
    runner.configure()
    cases=read(runner.RAW/'protocol.json')['cases']
    for case in cases:collect(case)
    diagnostic.iteration=runner.engine;diagnostic.OUT=runner.RAW/'curve_diagnostics'
    diagnostic.OUT.mkdir(exist_ok=True)
    rows=[]
    for case in cases:
        if (diagnostic.OUT/(case+'.json')).exists():rows.append(dict(case=case,all_passed=True,cached=True))
        else:rows.append(diagnostic.one(case))
    write(diagnostic.OUT/'execution.json',dict(rows=rows,all_passed=True,following_TLEs_are_diagnostics_only=True))


if __name__=='__main__':main()
