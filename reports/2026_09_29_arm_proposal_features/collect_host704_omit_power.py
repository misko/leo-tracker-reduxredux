"""Collect full saved-IQ omit-power proposal rows for final-reuse geometry."""
import ast
import hashlib
import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUTS = Path('/var/tmp/leo-ds7-large-arm-20260928')
ORACLE = Path('/var/tmp/leo-arm-full-search-oracle-allrates')


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def payload(path):
    data = path.read_bytes(); assert data[:6] == b'\x93NUMPY'
    size, offset = (struct.unpack_from('<H', data, 8)[0], 10) if data[6] == 1 else (struct.unpack_from('<I', data, 8)[0], 12)
    header = ast.literal_eval(data[offset:offset+size].decode('latin1'))
    assert header['descr'] == '<i2' and not header['fortran_order']
    raw = data[offset+size:]; assert len(raw) == 2*math.prod(header['shape'])
    return raw


def main():
    out = HERE/'host704-omit-power-v1'; out.mkdir(exist_ok=False)
    binary = HERE/'builds/host/proposal_feature_ablation'; receipt = binary.parent/'build-receipt.json'
    build = json.loads(receipt.read_text()); assert sha(binary) == build['binaries'][binary.name]
    inputs = json.loads((INPUTS/'inputs.json').read_text()); assert inputs['complete'] and len(inputs['rows']) == 704
    oracle = json.loads((ORACLE/'oracle.json').read_text())
    templates = {(case['context']['rate_hz'], case['context']['target']['edge']): ORACLE/case['templates']['exact']['file'] for case in oracle['cases']}
    for path in templates.values(): assert path.exists()
    rows = []; timings = []
    with tempfile.TemporaryDirectory(prefix='feature-omit-power-') as temporary:
        raw = Path(temporary)/'dwell.ci16'
        for ordinal, context in enumerate(inputs['rows']):
            source = INPUTS/context['file']; assert sha(source) == context['sha256']
            raw.write_bytes(payload(source))
            template = templates[(context['rate_hz'], context['target']['edge'])]
            result = subprocess.run([str(binary), str(context['rate_hz']), str(template), str(raw), '--combined-only', '--omit=power'], check=True, text=True, capture_output=True)
            actual = list(map(json.loads, result.stdout.splitlines())); assert len(actual) == 22
            for row in actual:
                assert row['feature_mask'] == ['lag1', 'lag3', 'lag5']
                rows.append({'context': context, 'window': row['probe_index'], 'rx': row['receiver_id'], 'ranked_epochs': {'combined': row['top4']['combined']}})
                timings.append(row['timings_ms']['total'])
            print('processed', ordinal, flush=True)
    output = out/'rows.jsonl'; output.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    summary = {'complete': True, 'scope': 'host saved-IQ proposal collection only; no GLRT or RF',
               'binary_sha256': sha(binary), 'build_receipt_sha256': sha(receipt), 'contexts': 704, 'windows': len(rows),
               'rates_hz': sorted({c['rate_hz'] for c in inputs['rows']}), 'feature_mask': ['lag1','lag3','lag5'],
               'rows_sha256': sha(output), 'mean_host_cpu_ms_per_window': sum(timings)/len(timings)}
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary), flush=True)


if __name__ == '__main__': main()
