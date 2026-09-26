"""Bounded standalone numerical and artifact validation; no raw IQ required."""
from pathlib import Path
import json
import re
import numpy as np
from geometry import incidence_projection, wrap_radians, C_M_PER_S, TAU
from scoring import fit_single_candidate, fit_double_difference

HERE=Path(__file__).resolve().parent

def main():
    checks=[]
    rows=json.loads((HERE/'measurements.json').read_text())['measurements']
    pairs=json.loads((HERE/'double-differences.json').read_text())['rows']
    assert len(rows)==72 and len(pairs)==36
    lookup={(r['visit_index'],r['window_start_sample'],r['mode']):r for r in rows}
    assert len(lookup)==72
    for p in pairs:
        a=lookup[p['visit_index'],p['window_start_sample'],0]
        b=lookup[p['visit_index'],p['window_start_sample'],1]
        np.testing.assert_allclose(p['mode1_minus_mode0_phase_rad'],wrap_radians(b['rx1_minus_rx0_phase_rad']-a['rx1_minus_rx0_phase_rad']),atol=1e-12)
        assert a['utc_estimate_ns']==b['utc_estimate_ns']
    for r in rows:
        assert r['utc_earliest_ns'] < r['utc_estimate_ns'] < r['utc_latest_ns']
        np.testing.assert_allclose(r['wavelength_m'],C_M_PER_S/r['physical_rf_estimate_hz'])
    checks.append('real row counts, simultaneous subtraction, UTC brackets and RF-to-wavelength conversion')
    np.testing.assert_allclose(incidence_projection([79,169],0),[1,0],atol=1e-14)
    checks.append('scalar elevation broadcasts over azimuth array; 79-degree axis convention')
    t=np.linspace(0,1,24);u=.1+.4*t**2;rf=np.full(24,11.2e9);train=np.arange(24)%3!=0
    phase=wrap_radians(TAU*.8*rf*u/C_M_PER_S+.4)
    first=fit_single_candidate(phase,u,rf,train,[.7,.8,.9])
    changed=phase.copy();changed[~train]=wrap_radians(changed[~train]+1.1)
    second=fit_single_candidate(changed,u,rf,train,[.7,.8,.9])
    assert first['baseline_length_m']==second['baseline_length_m']==.8
    assert first['instrumental_phase_rad']==second['instrumental_phase_rad']
    assert first['held_loss']<1e-12 and second['held_loss']>.1
    checks.append('held observations cannot change trained baseline or phase intercept')
    dd=fit_double_difference(wrap_radians(TAU*.8*rf*u/C_M_PER_S),rf*u/C_M_PER_S,train,[.7,.8,.9])
    assert dd['baseline_length_m']==.8 and dd['held_loss']<1e-12
    checks.append('known-truth double difference recovers baseline without an intercept')
    benchmark=json.loads((HERE/'randomized-benchmark.json').read_text())
    groups=np.array(benchmark['group_assignments']);mask=np.array(benchmark['train_mask'])
    for group in set(groups): assert len(set(mask[groups==group]))==1
    results=benchmark['results']
    assert results['True direction']['held_loss']<min(r['held_loss'] for n,r in results.items() if n!='True direction')
    checks.append('seeded benchmark keeps whole groups intact and true candidate wins')
    for target in re.findall(r'\]\(([^)]+)\)',(HERE/'README.md').read_text()):
        if target=='validation.json': continue  # Written below by this validation run.
        assert (HERE/target).is_file(), target
    checks.append('all report links and images resolve within standalone directory')
    receipt=dict(status='passed',checks=checks,check_count=len(checks),limitations='These checks do not validate real geometric phase truth.')
    (HERE/'validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
