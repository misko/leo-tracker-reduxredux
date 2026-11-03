"""Bounded saved-DS9 replay of the three hash-qualified native ARM binaries."""
import hashlib
import io
import json
import math
import random
import shlex
import statistics
import subprocess
import tarfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PRIOR = Path('/var/tmp/leo-arm-realtime-publication/reports/2026_09_29_arm_sparse_headroom')
INPUTS = Path('/var/tmp/leo-lag-discovery-ds9-v1')
ORACLE = Path('/var/tmp/leo-arm-full-search-oracle-allrates')
ROOT = '/mnt/glrtbench/ds9-native-comparison-20260930'
SEED = 2026093001
BUILDS = {
    'control': ('fullprep-uncached', '/var/tmp/leo-native-glrt-headroom-fullprep-uncached-final-v2'),
    'ordinary': ('sparse-reuse-plans', '/var/tmp/leo-native-glrt-headroom-final-v3-frozen'),
    'pgo': ('sparse-reuse-plans-pgo33', '/var/tmp/leo-native-glrt-headroom-pgo-use-v3-frozen'),
}
SSH = ['sudo', '-n', 'sshpass', '-f', '/etc/leo/credentials/scanner-iiod-ssh-password']
OPTIONS = ['-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=10', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def remote(command, timeout=60):
    return subprocess.check_output([*SSH, 'ssh', *OPTIONS, 'root@192.168.1.15', command], text=True, timeout=timeout)


def upload(path, destination):
    subprocess.run([*SSH, 'scp', '-O', *OPTIONS, str(path), 'root@192.168.1.15:' + destination], check=True, capture_output=True, timeout=180)
    assert remote('sha256sum ' + shlex.quote(destination)).split()[0] == sha(path)


def scientific(rows):
    # Only row-level timing is removed; all candidates and counters are retained.
    return [{k: v for k, v in row.items() if k != 'timings_ms'} for row in rows]


def distribution(values):
    ordered = sorted(values)
    return dict(mean=statistics.mean(values), p50=statistics.median(values),
                p95=ordered[math.ceil(.95 * len(values)) - 1], maximum=max(values),
                over_100ms=sum(v > 100 for v in values), at_least_120ms=sum(v >= 120 for v in values))


def main():
    started = time.monotonic()
    local = HERE / 'local'
    local.mkdir(exist_ok=True)
    assert not (HERE / 'panel.json').exists(), 'Use a fresh report directory for a new run'
    manifest = INPUTS / 'inputs.json'
    cases = [x for x in json.loads(manifest.read_text())['rows'] if x['rate_hz'] == 2500000]
    assert len(cases) == 80 and all(x['dataset_id'] == 'DS9' for x in cases)
    assert len({(x['session_id'], x['visit_index']) for x in cases}) == len(cases)
    prior = json.loads((PRIOR / 'panel.json').read_text())
    templates = {}
    for item in prior['selected']:
        templates.setdefault(item['context']['target']['edge'], item['templates'])
    payloads = {}
    for edge, roles in templates.items():
        for role, item in roles.items():
            source = ORACLE / item['file']
            assert sha(source) == item['sha256']
            payloads[edge + '-' + role + '.c128'] = source.read_bytes()
    for case in cases:
        source = INPUTS / case['file']
        assert sha(source) == case['sha256']
        values = np.load(source, allow_pickle=False)
        assert values.dtype == np.dtype('<i2') and values.shape == (300000, 2, 2)
        raw = values.tobytes()
        case['raw_sha256'] = hashlib.sha256(raw).hexdigest()
        case['raw_file'] = case['raw_sha256'] + '.ci16'
        payloads[case['raw_file']] = raw
    rng = random.Random(SEED)
    groups = []
    for edge in ('lower', 'upper'):
        subset = sorted((c for c in cases if c['target']['edge'] == edge), key=lambda c: (c['session_id'], c['visit_index']))
        rng.shuffle(subset)
        for offset in range(0, len(subset), 8):
            batch = subset[offset:offset + 8]
            calls = []
            lines = []
            for repeat in range(10):
                order = list(range(len(batch)))
                rng.shuffle(order)
                for i in order:
                    c = batch[i]
                    seq = len(calls)
                    calls.append(dict(sequence=seq, repeat=repeat, case=c))
                    lines.append('\t'.join(map(str, [seq, 2500000, 120, 120, ROOT+'/'+edge+'-exact.c128', ROOT+'/'+edge+'-control.c128', ROOT+'/'+c['raw_file']])))
            name = f'{edge}-{offset:03d}'
            payloads[name+'.tsv'] = ('\n'.join(lines)+'\n').encode()
            groups.append(dict(id=name, calls=calls))
    bindings = {}
    for label, (old_label, directory) in BUILDS.items():
        expected = json.loads((PRIOR/'local'/old_label/'binding.json').read_text())
        binary = Path(directory)/'leo-native-glrt-bench'
        receipt = Path(directory)/'build-receipt.json'
        assert sha(binary) == expected['binary_sha256']
        assert sha(receipt) == expected['receipt_sha256']
        payloads['bench-'+label] = binary.read_bytes()
        (HERE/(label+'-build-receipt.json')).write_bytes(receipt.read_bytes())
        bindings[label] = dict(binary_sha256=sha(binary), receipt_sha256=sha(receipt), source_directory=directory)
    hashes = {k: hashlib.sha256(v).hexdigest() for k,v in payloads.items()}
    payloads['inputs.sha256'] = ''.join(f'{v}  {k}\n' for k,v in hashes.items()).encode()
    save(HERE/'panel.json', dict(seed=SEED, rounds=10, selection='All 80 saved 2.5 MS/s dwells in the existing DS9 input manifest; no selection by measured output', input_manifest_sha256=sha(manifest), templates=templates, cases=cases, groups=groups, builds=bindings, files=hashes, runner_sha256=sha(__file__)))
    bundle = local/'inputs.tar'
    with tarfile.open(bundle, 'w') as archive:
        for name, data in payloads.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    (HERE/'device-before.txt').write_text(remote('date -u; uptime; cat /proc/cpuinfo; cat /proc/meminfo; ps; sha256sum /usr/lib/libfftw3.so.3'))
    assert '1331a476804e5812490f15c18f4b087859552716fb5933413606482642d61a19' in (HERE/'device-before.txt').read_text()
    remote('mkdir -p ' + ROOT)
    upload(bundle, ROOT+'/inputs.tar')
    remote('cd '+ROOT+' && tar -xf inputs.tar && sha256sum -c inputs.sha256 && chmod +x bench-*', 180)
    print(f'Staged {len(cases)} DS9 dwells, {len(groups)} batches; all build/input hashes verified', flush=True)
    results = {k: [] for k in BUILDS}
    labels = list(BUILDS)
    execution_order = []
    for index, group in enumerate(groups):
        # Rotate build order to distribute temperature/order effects.
        order = labels[index % 3:] + labels[:index % 3]
        for label in order:
            assert time.monotonic() - started < 900, 'Bounded replay exceeded 15 minutes'
            command = [ROOT+'/bench-'+label, '--manifest', ROOT+'/'+group['id']+'.tsv', '--thermal-path', '/sys/bus/iio/devices/iio:device1/in_temp0_raw', '--thermal-offset', '-2219', '--thermal-scale', '123.040771484']
            output = remote('ulimit -v 220000; ' + shlex.join(command), 60)
            path = local/(label+'-'+group['id']+'.jsonl')
            path.write_text(output)
            rows = [json.loads(line) for line in output.splitlines()]
            assert rows[0]['kind'] == 'setup' and rows[-1]['kind'] == 'summary'
            assert len(rows) == len(group['calls']) + 2
            for emitted, mapping in zip(rows[1:-1], group['calls'], strict=True):
                result = emitted['result']
                assert result['sequence'] == mapping['sequence']
                assert (result['rate_hz'], result['dwell_ms'], result['stride_ms']) == (2500000,120,120)
                assert len(result['rows']) == 2
                results[label].append((mapping, emitted))
            execution_order.append(dict(group=group['id'], build=label, sha256=sha(path)))
            print(label, group['id'], len(rows)-2, 'calls complete', flush=True)
    control = {}
    mismatches = []
    unique = {}
    summaries = {}
    for label, entries in results.items():
        for mapping, emitted in entries:
            c = mapping['case']
            key = (c['session_id'], c['visit_index'])
            normalized = scientific(emitted['result']['rows'])
            if label == 'control' and key not in control:
                control[key] = normalized
                unique[key] = emitted['result']['rows']
            if normalized != control[key]:
                mismatches.append(dict(build=label, session_id=key[0], visit_index=key[1], repeat=mapping['repeat']))
        summaries[label] = dict(calls=len(entries), cpu_ms=distribution([e['result']['call_cpu_ms'] for _,e in entries]), wall_ms=distribution([e['result']['call_wall_ms'] for _,e in entries]), max_rss_kib=max(e['result']['peak_rss_kib_after'] for _,e in entries))
    all_rows = [r for rows in unique.values() for r in rows]
    all_candidates = [c for r in all_rows for c in r['candidates']]
    summary = dict(dataset='DS9', unique_dwells=len(unique), unique_scans=len({k[0] for k in unique}), unique_receiver_windows=len(all_rows), candidate_entries=len(all_candidates), positive_candidates=sum(c['margin'] >= .025 for c in all_candidates), positive_windows=sum(any(c['margin'] >= .025 for c in r['candidates']) for r in all_rows), mismatches=mismatches, builds=summaries, execution_order=execution_order, elapsed_seconds=time.monotonic()-started, scope='Persistent RAM detector, CPU0, 2.5 MS/s, 120 ms dwell, 120 ms stride; first calls included; no RF capture or production integration')
    save(HERE/'summary.json', summary)
    (HERE/'device-after.txt').write_text(remote('date -u; uptime; cat /proc/meminfo; sha256sum /usr/lib/libfftw3.so.3'))
    print(json.dumps({k:v for k,v in summary.items() if k != 'execution_order'}, indent=2), flush=True)
    assert not mismatches, 'Scientific mismatch; inspect saved evidence'


if __name__ == '__main__':
    main()
