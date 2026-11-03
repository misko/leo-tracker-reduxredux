"""Freeze online-assembled measurement receipts after the IQ runner exits.

The runner also writes a final aggregate. Require identical scientific records,
top rows and signatures, preserve both execution summaries, and restore the
exact snapshot used by already-running numerical fits. Execution-time summation
order is allowed to differ; numerical data and algorithm identities are not.
"""
import json
import hashlib
from pathlib import Path

HERE=Path(__file__).resolve().parent


def main():
    for i in range(1,17):
        scan=f'N{i:02}';folder=HERE/'refinement'/scan
        frozen=folder/'frozen-refined.json';target=folder/'refined.json'
        if not frozen.exists():raise ValueError(f'{scan}: online snapshot not yet available')
        a=json.loads(frozen.read_text());b=json.loads(target.read_text())
        assert a['records']==b['records'] and a['top_rows']==b['top_rows']
        for key in a['summary']:
            if key=='compute_s':continue
            assert a['summary'][key]==b['summary'][key],(scan,key)
        (folder/'runner-final-summary.json').write_text(json.dumps(b['summary'],indent=2))
        cal_path=HERE/'pass2'/scan/'calibration.json'
        if not cal_path.exists():raise ValueError(f'{scan}: wait for the calibration receipt before finalizing')
        expected=json.loads(cal_path.read_text())['observations'][str(target)].removeprefix('sha256:')
        first,last=frozen.read_bytes(),target.read_bytes()
        if hashlib.sha256(first).hexdigest()==expected:
            if first!=last:target.write_bytes(first)
        elif hashlib.sha256(last).hexdigest()==expected:
            # This scan began after the final aggregate was already written.
            (folder/'online-assembled-summary.json').write_text(json.dumps(a['summary'],indent=2))
            frozen.write_bytes(last)
        else:raise ValueError(f'{scan}: calibration is bound to neither complete snapshot')
        print('FROZEN',scan,len(a['records']))


if __name__=='__main__':main()
