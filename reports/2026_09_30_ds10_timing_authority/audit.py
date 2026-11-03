import hashlib
import importlib.util
import json
from pathlib import Path
from statistics import median


def main():
    here=Path(__file__).resolve().parent
    module_path=here.parent/'2026_09_29_timing_authority/audit.py'
    spec=importlib.util.spec_from_file_location('timing_audit',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    path=here/'metadata.json';data=json.loads(path.read_text())
    for p,digest in data['hashes'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest
    rows=[dict(session_id=r['session_id'],**module.audit(r)) for r in data['rows']]
    valid=[r for r in rows if r['status']=='ok']
    summary={'scans':len(rows),'timing_present':len(valid),'qualified':sum(r['qualified'] for r in valid),
             'outside_host_bracket':sum(r['outside_distance_s']>0 for r in valid)}
    for field in ('bracket_width_s','spread_us','outside_distance_s','counter_duration_s'):
        values=[r[field] for r in valid]
        summary[field]={'min':min(values),'median':median(values),'max':max(values)} if values else None
    if valid:
        lower=max(r['fitted_tau_s']-r['upper_offset_s'] for r in valid)
        upper=min(r['fitted_tau_s']-r['lower_offset_s'] for r in valid)
        summary['common_bias_interval']={'lower_s':lower,'upper_s':upper,'feasible':lower<=upper,'gap_s':max(lower-upper,0)}
    sources=[path,module_path,Path(__file__),here/'export.py',here/'PROTOCOL.md']
    with (here/'results.json').open('x') as f:json.dump(dict(rows=rows,summary=summary,source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),f,indent=2)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
