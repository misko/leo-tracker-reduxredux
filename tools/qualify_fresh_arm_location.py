"""Qualify local ARM observation/graph/track composition and two-site scoring.

Uses existing recorded replay products. Fixed comparison sites are diagnostics,
not a regional position search or a claim of independent physical truth.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess

from leo.native_pipeline.runner import digest, finite_json, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('replay', 'tracking', 'authority', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    execution = finite_json(args.replay/'execution.json')
    protocol = finite_json(args.replay/'protocol.json')
    tracking = finite_json(args.tracking/'receipt.json')
    authority = finite_json(args.authority/'authority.json')
    if execution['exit_code'] != 0 or tracking['status'] != 'complete':
        raise ValueError('upstream stages are incomplete')
    if digest(args.replay/'protocol.json') != execution['protocol_sha256']:
        raise ValueError('replay protocol changed')
    inputs = {'observations': args.replay/'observations.tsv',
              'graph': args.replay/'graph.tsv', 'tracks': args.tracking/'tracks.tsv',
              'authority': args.authority/'authority.loc1'}
    for key in ('observations', 'graph'):
        if digest(inputs[key]) != execution[key+'_sha256']:
            raise ValueError('replay checkpoint changed: '+key)
    if digest(inputs['observations']) != tracking['input_sha256']:
        raise ValueError('tracker used different observations')
    if digest(inputs['authority']) != authority['files']['authority.loc1']:
        raise ValueError('orbit authority changed')
    if protocol['projection']['capture_digest'] != authority['capture_digest']:
        raise ValueError('capture identities differ')
    if not args.output.name.replace('-', '').isalnum():
        raise ValueError('invalid diagnostic directory name')
    args.output.mkdir(parents=True, exist_ok=False)
    host_pipeline = Path('/var/tmp/leo-modular-pipeline-host/leo-adaptive-pipeline')
    arm_pipeline = Path('/var/tmp/leo-modular-pipeline-arm/leo-adaptive-pipeline')
    host_location = Path('/var/tmp/leo-modular-location-host/leo-location')
    arm_location = Path('/var/tmp/leo-modular-location-arm/leo-location')

    def run(argv):
        return subprocess.run(list(map(str, argv)), capture_output=True, text=True,
                              check=True, timeout=150)

    host_input = args.output/'host.loc1'
    result = run([host_pipeline, inputs['observations'], inputs['graph'],
                  inputs['authority'], host_input, '--tracks', inputs['tracks'],
                  '--exclusive-candidates'])
    (args.output/'host-conversion.stdout').write_text(result.stdout)
    (args.output/'host-conversion.stderr').write_text(result.stderr)
    result = run([host_location, 'score', host_input, '2'])
    (args.output/'host-score.json').write_text(result.stdout)
    (args.output/'host-score.stderr').write_text(result.stderr)
    host_score = json.loads(result.stdout)
    auth = ['sudo', '-n', 'sshpass', '-f',
            '/etc/leo/credentials/scanner-iiod-ssh-password']
    options = ['-o', 'LogLevel=ERROR', '-o', 'ConnectTimeout=10', '-o',
               'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile='+str(root/
               'reports/2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh = auth+['ssh']+options+['root@192.168.1.15']
    q = shlex.quote

    def remote(argv):
        return run(ssh+[' '.join(q(str(v)) for v in argv)])

    if '/modular-ds9-iq-v1/leo-recorded-' in remote(['ps']).stdout:
        raise ValueError('paced measurement still active')
    directory = '/mnt/glrtbench/'+args.output.name
    device = {key: protocol['device_iq_directory']+'/'+protocol['projection'][key+'_name']
              for key in ('observations', 'graph')}
    device['tracks'] = '/mnt/glrtbench/'+args.tracking.name+'/tracks.tsv'
    # These products remain on ARM. Downloads above are evaluation copies only.
    for key, path in device.items():
        if remote(['sha256sum', path]).stdout.split()[0] != digest(inputs[key]):
            raise ValueError('device checkpoint changed: '+key)
    remote(['mkdir', directory])
    payloads = {'pipeline': arm_pipeline, 'location': arm_location,
                'authority': inputs['authority']}
    for name, path in payloads.items():
        run(auth+['scp', '-O']+options+[path, 'root@192.168.1.15:'+directory+'/'+name])
        if remote(['sha256sum', directory+'/'+name]).stdout.split()[0] != digest(path):
            raise ValueError('device payload differs: '+name)
    remote(['chmod', '755', directory+'/pipeline', directory+'/location'])
    measure = '/mnt/glrtbench/native-adaptive/current/measure-run'
    result = remote([measure, 90, directory+'/pipeline', device['observations'],
                     device['graph'], directory+'/authority', directory+'/input.loc1',
                     '--tracks', device['tracks'], '--exclusive-candidates'])
    (args.output/'conversion.stdout').write_text(result.stdout)
    (args.output/'conversion.stderr').write_text(result.stderr)
    timings = []

    def timing(stderr):
        return next(json.loads(line) for line in stderr.splitlines()
                    if line.startswith('{') and json.loads(line).get('scope') == 'whole_process')

    timings.append({'stage': 'track_support_conversion', **timing(result.stderr)})
    for suffix in ('', '.tracks.tsv', '.members.tsv'):
        if remote(['sha256sum', directory+'/input.loc1'+suffix]).stdout.split()[0] != digest(Path(str(host_input)+suffix)):
            raise ValueError('host/ARM converted output differs: '+suffix)
    result = remote([measure, 90, directory+'/location', 'score', directory+'/input.loc1', 2])
    (args.output/'score.json').write_text(result.stdout)
    (args.output/'score.stderr').write_text(result.stderr)
    timings.append({'stage': 'two_fixed_site_scores', **timing(result.stderr)})
    exact = json.loads(result.stdout) == host_score
    receipt = {'status': 'complete' if exact else 'failed',
               'host_arm_conversion_bytes_exact': True, 'host_arm_scores_exact': exact,
               'input_sha256': {key: digest(path) for key, path in inputs.items()},
               'payload_sha256': {key: digest(path) for key, path in payloads.items()},
               'host_binary_sha256': {'pipeline': digest(host_pipeline), 'location': digest(host_location)},
               'timings': timings, 'selection_policy': 'exclusive-candidates-longest-v1',
               'scope': 'Fresh ARM-local observations, support and tracks; two fixed diagnostic sites, not regional positioning or sustained overlap'}
    write_json(args.output/'receipt.json', receipt)
    print(json.dumps(receipt))
    if not exact:
        raise ValueError('host/ARM scores differ')


if __name__ == '__main__':
    main()
