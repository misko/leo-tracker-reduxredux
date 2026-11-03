"""Two-dwell recorded-IQ staging smoke check on the authorized PLUTO+."""
import argparse
import json
from pathlib import Path
import subprocess

from leo.native_pipeline.runner import digest,finite_json,write_json


def command(argv):
    return subprocess.run(list(map(str,argv)),capture_output=True,text=True,check=True,timeout=90)


def scientific_rows(call):
    # This one documented field is measurement telemetry, not detector output.
    return [{k:v for k,v in row.items() if k!='timings_ms'} for row in call['rows']]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--iq',type=Path,required=True)
    p.add_argument('output',type=Path);args=p.parse_args()
    root=Path(__file__).resolve().parents[1];reports=root/'reports'
    inventory=finite_json(args.iq/'inventory.json')
    args.output.mkdir(parents=True,exist_ok=False)
    if not args.output.name.replace('-','').isalnum():raise ValueError('invalid device directory name')
    remote='/mnt/glrtbench/'+args.output.name
    auth=['sudo','-n','sshpass','-f','/etc/leo/credentials/scanner-iiod-ssh-password']
    options=['-o','LogLevel=ERROR','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(reports/'2026_09_30_native_adaptive_deployment/firmware/private/192.168.1.15-v054.root.known_hosts')]
    ssh=auth+['ssh']+options+['root@192.168.1.15']
    command(ssh+['mkdir '+remote])
    binary='/mnt/glrtbench/missing-long-gate-ablation-20261001/bench-ungated'
    local_binary=reports/'2026_10_01_arm_glrt_missing_diagnosis/ungated-build/leo-native-glrt-bench'
    if command(ssh+['sha256sum '+binary]).stdout.split()[0]!=digest(local_binary):
        raise ValueError('device binary differs')
    templates='/mnt/glrtbench/ds9-native-comparison-20260930'
    panel=finite_json(reports/'2026_09_30_arm_ds9_native_comparison/panel.json')
    lines=[]
    for row in inventory[:2]:
        path=args.iq/row['path']
        if digest(path)!=row['raw_sha256']:raise ValueError('staged IQ differs')
        command(auth+['scp','-O']+options+[path,'root@192.168.1.15:'+remote+'/'+path.name])
        if command(ssh+['sha256sum '+remote+'/'+path.name]).stdout.split()[0]!=row['raw_sha256']:
            raise ValueError('device IQ differs')
        edge=row['event']['target']['edge']
        for role in ['exact','control']:
            actual=command(ssh+['sha256sum '+templates+'/'+edge+'-'+role+'.c128']).stdout.split()[0]
            if actual!=panel['templates'][edge][role]['sha256']:raise ValueError('template differs')
        lines.append('\t'.join(map(str,[row['visit'],2500000,120,120,
            templates+'/'+edge+'-exact.c128',templates+'/'+edge+'-control.c128',remote+'/'+path.name])))
    manifest=args.output/'batch.tsv';manifest.write_text('\n'.join(lines)+'\n')
    command(auth+['scp','-O']+options+[manifest,'root@192.168.1.15:'+remote+'/batch.tsv'])
    actual=command(ssh+[binary+' --manifest '+remote+'/batch.tsv'])
    (args.output/'detector.jsonl').write_text(actual.stdout)
    calls=[d['result'] for line in actual.stdout.splitlines() if 'result' in (d:=json.loads(line))]
    baseline=reports/'2026_10_01_arm_ungated_full_scan/arm/batch-000000.jsonl'
    expected=[d['result'] for line in baseline.read_text().splitlines() if 'result' in (d:=json.loads(line))][:2]
    if len(calls)!=2 or any(a['sequence']!=b['sequence'] or scientific_rows(a)!=scientific_rows(b) for a,b in zip(calls,expected)):
        raise ValueError('fresh ARM detector rows differ from qualified output')
    receipt={'status':'complete','scope':'First two recorded dwells; local IQ during execution; not paced qualification',
             'binary_sha256':digest(local_binary),'baseline_sha256':digest(baseline),
             'visits':[r['visit'] for r in inventory[:2]],'all_scientific_detector_rows_identical':True,
             'excluded_row_fields':['timings_ms'],
             'call_wall_ms':[c['call_wall_ms'] for c in calls]}
    write_json(args.output/'receipt.json',receipt);print(json.dumps(receipt))


if __name__=='__main__':main()
