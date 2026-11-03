import csv,json,sys
from pathlib import Path
import numpy as np
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'2026_10_07_recent_filter_review'))
from analyze import coordinates,error_vector

def main():
    result=json.loads((HERE/'results.json').read_text())
    snapshot=json.loads((HERE.parent/'2026_10_07_recent_filter_review/snapshot.json').read_text())
    doc=next(x for x in snapshot['captures'] if x['session_id']==result['session_id'])['regional_document']
    store=ScannerTrackingInputStore(Path('/srv/bulk/leo'))
    try: source=store.load(result['session_id'])
    finally: store.close()
    assert source.input_manifest_sha256==doc['input_manifest_sha256']
    assert source.analysis_manifest_sha256==doc['analysis_manifest_sha256']
    errors=[]
    for row in result['repriced']:
        if row['sigma']!=.15 or row['method']!='V16': continue
        saved=next(r for r in doc['diagnostics']['final_starts'] if all(r[k]==row[k] for k in ('basin','method','arm','start')))
        errors.append(abs(saved['fit']['objective']-row['objective']))
    assert max(errors)<1e-6
    table=[]
    for row in result['fits']:
        lat,lon=coordinates(*row['fit']['vector'][:2])
        row['error_m']=float(np.linalg.norm(error_vector(lat,lon,doc['reference_latitude_deg'],doc['reference_longitude_deg'])))
    for sigma in (.15,.5,1.):
        for arm in ('zero-c','fitted-c'):
            row=min((r for r in result['fits'] if r['sigma']==sigma and r['arm']==arm),key=lambda r:r['total'])
            table.append(dict(sigma=sigma,arm=arm,basin=row['basin'],total=row['total'],data_nll=row['data_nll'],error_m=row['error_m'],rms_hz=row['fit']['posterior_rms_hz'],signal_fraction=row['fit']['signal_windows']/result['observations'],converged=row['fit']['converged'],stop=row['fit']['stop_reason']))
    gaps=[]
    for sigma in (.15,.5,1.):
        for basin in ('point:-56.25:-68.75','point:-93.75:-81.25'):
            arms={a:min((r for r in result['fits'] if r['sigma']==sigma and r['basin']==basin and r['arm']==a),key=lambda r:r['total']) for a in ('zero-c','fitted-c')}
            gaps.append(dict(sigma=sigma,basin=basin,free_minus_feasible_zero=arms['fitted-c']['total']-arms['zero-c']['total']))
    audit=dict(input_hash=source.input_manifest_sha256,analysis_hash=source.analysis_manifest_sha256,max_archived_v16_discrepancy=max(errors),selected=table,nested_gaps=gaps)
    (HERE/'audit.json').write_text(json.dumps(audit,indent=2))
    (HERE/'results.json').write_text(json.dumps(result,indent=2))
    with (HERE/'selected.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    print(json.dumps(audit,indent=2))

if __name__=='__main__': main()
