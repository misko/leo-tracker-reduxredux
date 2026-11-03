"""Audit the fast comparator roster, causal orbit bytes and pinned numerical sources."""
import subprocess,platform
from common import *
def main():
    roster=read(ROOT/'roster.json');m=read(ROOT/'dataset/manifest.json')
    assert digest(ROOT/'dataset/manifest.json')==roster['parent_dataset_manifest_sha256'].removeprefix('sha256:')
    fast=[r for r in m['members'] if r['recording_format']=='short_window_iq_recording']
    assert {r['dataset_label'] for r in fast}=={r['case'] for r in roster['cases']}
    assert len(fast)==34 and len({r['raw_recording']['identity_sha256'] for r in fast})==34
    available=read(ROOT/'input-availability.json')['rows'];old={r['case']:r for r in roster['cases']}
    unhandled=[r['case'] for r in available if r['status']=='exported' and old[r['case']]['input'] is None]
    assert not unhandled,('New GLRT input needs evaluation',unhandled)
    checks=[]
    for row in read(ROOT/'protocol.json')['cohort']:
        case=row['case'];z=read(ROOT/'inputs'/(case+'.json'));native=Path(z['native_path'])
        cat=read(ROOT/'catalogues'/(case+'.json'))['elements'];nom=read(native/'nominal_elements.json');cutoff=z['scan_receipt']['cutoff_utc_ns']
        assert all(0<=(cutoff-v[k])/3.6e12<=72 for v in cat.values() for k in ('element_epoch_utc_ns','collected_utc_ns'))
        assert all(n in cat and cat[n]['lines']==v['lines'] for n,v in nom.items())
        assert not z['scan_receipt']['reference_position_used']
        assert z['scan_receipt']['search_center']==[37.906,-122.545] and z['scan_receipt']['search_box_width_km']==25
        checks.append(dict(case=case,causal_elements=len(cat),nominal_elements_identical=len(nom)))
    write(ROOT/'input-audit.json',dict(roster_verified=True,fast_comparison_count=34,adaptive_used=False,new_unhandled_GLRT_inputs=unhandled,scans=checks))
    import scipy,sgp4
    files=[p for directory in ('src','tools') for p in (RELEASE/directory).rglob('*.py')]
    write(ROOT/'numerical-provenance.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RELEASE,text=True).strip(),
        python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,sgp4=sgp4.__version__,
        source_sha256={str(p.relative_to(RELEASE)):digest(p) for p in files},prior_common_sha256=digest(PREVIOUS/'common.py'),
        production_changed=False,matched_c_arms=True))
    print('Audited',len(checks),'baseline scans and',sum(v['nominal_elements_identical'] for v in checks),'nominal TLEs')
if __name__=='__main__':main()
