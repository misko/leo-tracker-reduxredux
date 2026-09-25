"""Review paced ARM observer jobs and every retained original-IQ byte."""
import json
from pathlib import Path
import numpy as np
from check_adjacent_c_validity import BASE, digest
from review_tracking_cadences_arm import SSH_ADVISORY


def main():
    output=BASE/'paced-observer-arm-v1-results'
    op=json.loads((output/'operator.json').read_text())
    build=json.loads((BASE/'paced-observer-build-v1.json').read_text())
    assert op['status']=='complete_review_pending' and op['temporary_files_removed']
    assert op['before']==op['after'] and op['serial']=='1040005e0b100007100010000bf33a5d4d'
    assert op['payload_sha256']==build['payloads']
    assert [r['offset'] for r in op['cases']]==[0,1,2]
    source=BASE/'paced-original-seed-input-v1/positive.ci16'
    assert digest(source)==build['payloads']['iq'];iq=source.read_bytes();cases=[]
    for case in op['cases']:
        assert case['exit_code']==0 and case['stderr'] in ('',SSH_ADVISORY)
        path=output/case['journal'];assert digest(path)==case['sha256']
        retained=output/f"o{case['offset']}.ci16"
        assert digest(retained)==case['retained_sha256']
        rows=[json.loads(line) for line in path.read_text().splitlines()];summary=rows.pop()
        host=[json.loads(line) for line in (BASE/'paced-observer-host-v1-results'/case['journal']).read_text().splitlines()]
        expected=host.pop();assert len(rows)==len(host)==200
        for key in ('offset','measurements','accepted','terminal_status'):assert summary[key]==expected[key]
        assert summary['terminal_status']==0 and summary['waits']>0
        assert 3300<=summary['maximum_source_age_samples']<=131072
        assert retained.read_bytes()==b''.join(iq[r['start']*4:(r['start']+3300)*4] for r in rows)
        for row,truth in zip(rows,host):
            for key in ('frame','start','phase','step','rejection'):assert row[key]==truth[key]
            for key in ('coherence','delay_s','cfo_hz'):
                np.testing.assert_allclose(row[key],truth[key],rtol=2e-10,atol=1e-12)
        cases.append(summary)
    result=dict(status='pass',cases=cases,verified_measurements=600,verified_retained_iq_bytes=7920000,
                producer_paced=True,live_RF_DMA_tested=False,native_tracking_qualified=False,
                reviewer_sha256=digest(Path(__file__)),operator_sha256=digest(output/'operator.json'))
    with (output/'review.json').open('x') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
