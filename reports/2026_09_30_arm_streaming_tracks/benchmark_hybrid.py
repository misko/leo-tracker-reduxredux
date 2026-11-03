"""Physical baseline includes coarse seed generation plus curvature extension."""
import json
from pathlib import Path
import shlex
from run_device import HERE,REMOTE,INPUTS,WRAPPER,AUTH,OPTIONS,SSH,run,sha


def main():
    old=HERE.parent/'2026_09_30_arm_curvature_tracks/hybrid-v1'
    out=HERE/'hybrid-device'
    out.mkdir(exist_ok=False)
    for label,path in [('hybrid-cli',old/'artifacts/leo-curvature-tracks-arm'),
                       ('hybrid-unit',old/'artifacts/test-curvature-tracks-arm')]:
        run(AUTH+['scp','-O']+OPTIONS+[str(path.resolve()),f'root@192.168.1.15:{REMOTE}/{label}'])
        run(SSH+[f'chmod 755 {REMOTE}/{label}'])
        assert run(SSH+[f'sha256sum {REMOTE}/{label}']).stdout.split()[0]==sha(path)
    unit=run(SSH+[f'{WRAPPER} 90 {REMOTE}/hybrid-unit'])
    (out/'unit.stdout').write_text(unit.stdout)
    (out/'unit.stderr').write_text(unit.stderr)
    coarse='/mnt/glrtbench/fast-tracks-f363-v1/grid-trial-arm-v3'
    coarse_local=HERE.parent/'2026_09_30_arm_fast_tracks/grid/grid-trial-arm-v3'
    assert run(SSH+['sha256sum '+coarse]).stdout.split()[0]==sha(coarse_local)
    inp=f'{INPUTS}/arm-observations.tsv'
    assert run(SSH+['sha256sum '+inp]).stdout.split()[0]==sha(
        HERE.parent/'2026_09_30_arm_fast_tracks/server-baseline/output/arm-observations.tsv')
    records=[]
    for i in range(3):
        seeds=f'{REMOTE}/hybrid-seeds.tsv'
        command=(f'{coarse} {inp} 151 8 512 8 4 16 > {seeds} && '
                 f'{REMOTE}/hybrid-cli {inp} --acceleration 250 --seeds {seeds}')
        r=run(SSH+[f'{WRAPPER} 90 /bin/sh -c '+shlex.quote(command)])
        path=out/f'arm-{i}.tsv';path.write_text(r.stdout)
        (out/f'arm-{i}.stderr').write_text(r.stderr)
        objects=[json.loads(line) for line in r.stderr.splitlines() if line.startswith('{')]
        seed_time=next(d['reconstruct_s'] for d in objects if 'reconstruct_s' in d)
        extension=next(float(line.split('\t')[2]) for line in r.stderr.splitlines()
                       if line.startswith('TIMING\treconstruct_s\t'))
        seed_equal=run(SSH+['sha256sum '+seeds]).stdout.split()[0]==sha(old/'seeds/arm.tsv')
        record={'repeat':i,'seed_tracking_s':seed_time,'extension_tracking_s':extension,
                'sum_tracking_s':seed_time+extension,'whole_process':next(d for d in objects if d.get('scope')=='whole_process'),
                'host_byte_identical':sha(path)==sha(old/'host/arm-a250-v2.tsv'),
                'seed_host_byte_identical':seed_equal}
        records.append(record);print(json.dumps(record),flush=True)
    (out/'receipt.json').write_text(json.dumps({'repetitions':records,
        'coarse_sha256':sha(coarse_local),'extension_sha256':sha(old/'artifacts/leo-curvature-tracks-arm'),
        'scope':'Both tracking stages included; whole process additionally includes startup, TSV seed writing/reading and final output'},indent=2)+'\n')


if __name__=='__main__':
    main()
