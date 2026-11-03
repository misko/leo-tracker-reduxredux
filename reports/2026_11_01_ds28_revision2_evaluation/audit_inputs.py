"""Check dataset boundaries, causal orbit identity, and baseline replay equivalence."""
import platform,subprocess
from common import *

def main():
    m=read(ROOT/'dataset/manifest.json');parent=read(ROOT/'dataset/parent-manifest.json')
    assert m['start_utc_ns']==parent['cutoff_utc_ns']
    assert m['dataset_id']=='DS28' and m['parent_dataset']=='DS27 revision 1'
    assert m['revision']==2
    previous=read(ROOT/'dataset/previous-revision-manifest.json')
    retained={r['raw_recording']['identity_sha256']:r['dataset_label'] for r in previous['members']}
    current={r['raw_recording']['identity_sha256']:r['dataset_label'] for r in m['members']}
    assert retained.items()<=current.items()
    assert len(m['members'])==len({r['raw_recording']['identity_sha256'] for r in m['members']})
    old={r['raw_recording']['identity_sha256'] for r in parent['members']}
    assert all(m['start_utc_ns']<=r['captured_utc_ns']<m['cutoff_utc_ns'] and
               r['recording_format']=='short_window_iq_recording' and r['raw_recording']['identity_sha256'] not in old for r in m['members'])
    checks=[];comparisons=[]
    for row in read(ROOT/'protocol.json')['cohort']:
        case=row['case'];z=read(ROOT/'inputs'/(case+'.json'));native=Path(z['native_path'])
        assert digest(z['baseline_source'])==z['baseline_sha256']
        cat=read(ROOT/'catalogues'/(case+'.json'))['elements'];nominal=read(native/'nominal_elements.json');cutoff=z['scan_receipt']['cutoff_utc_ns']
        for n,v in cat.items():
            assert all(0<=(cutoff-v[k])/3.6e12<=72 for k in ('element_epoch_utc_ns','collected_utc_ns'))
        assert all(n in cat and cat[n]['lines']==v['lines'] for n,v in nominal.items())
        assert not z['scan_receipt']['reference_position_used']
        assert z['scan_receipt']['search_center']==[37.906,-122.545] and z['scan_receipt']['search_box_width_km']==25
        checks.append(dict(case=case,causal_elements=len(cat),nominal_elements_identical=len(nominal),regional_prior_verified=True))
        p=WORK/'baselines'/case/'published-algo05.json'
        if p.exists():
            t=read(p);fresh=read(WORK/'baselines'/case/'terminal.json')
            assert fresh['decision']==t['decision'] and fresh['position']==t['position'] and fresh['candidate']==t['candidate']
            comparisons.append(dict(case=case,exact_public_decision_position_candidate=True))
    write(ROOT/'input-audit.json',dict(dataset_verified=True,scans=checks,published_baseline_comparisons=comparisons))
    import scipy,sgp4
    files=[p for directory in ('src','tools') for p in (RELEASE/directory).rglob('*.py')]
    write(ROOT/'numerical-provenance.json',dict(revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=RELEASE,text=True).strip(),
        python=platform.python_version(),numpy=np.__version__,scipy=scipy.__version__,sgp4=sgp4.__version__,
        source_sha256={str(p.relative_to(RELEASE)):digest(p) for p in files},
        prior_common_sha256=digest(PREVIOUS/'common.py'),read_only_recording_inputs=True,production_changed=False))
    print('Verified',len(checks),'scans;',sum(c['nominal_elements_identical'] for c in checks),'unchanged nominal elements',flush=True)

if __name__=='__main__':main()
