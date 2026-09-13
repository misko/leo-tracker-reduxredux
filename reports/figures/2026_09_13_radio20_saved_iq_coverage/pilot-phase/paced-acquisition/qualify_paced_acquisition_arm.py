"""Leased serial-bound ARM acquisition/observer replay, with no RF or native jobs."""
import hashlib,io,json,shlex,subprocess,sys,tarfile,uuid
from pathlib import Path
sys.path.insert(0,'/home/mouse9911/gits/plutosdr-fw-radio20-tracking/scripts')
from deploy_glrt_iq_tracking20 import EVIDENCE,PASSWORD
from leo.acquisition.authority import LocalCaptureAuthority,RadioResource,CaptureTaskKind
from pluto_plus import bootstrap_firmware as b,glrt_canary as g
from pluto_plus.glrt_iq_tracking_profiles import ENDPOINT
from pluto_plus.radio_lock import acquire_radio_lock

def main():
    output=Path(sys.argv[1]);output.mkdir(exist_ok=False)
    build=json.loads((EVIDENCE/'paced-acquisition-host-v2-results/result.json').read_text())
    files=dict(probe='paced-acquisition-arm-v2.bin',bank='coarse-bank.ci16',refs='direct-references.ci16',positive='paced-original-seed-input-v1/positive.ci16',control='paced-original-seed-input-v1/control.ci16')
    payload={k:(EVIDENCE/v).read_bytes() for k,v in files.items()}
    hashes={k:hashlib.sha256(data).hexdigest() for k,data in payload.items()}
    assert hashes['probe']==build['arm_sha256']
    for case in build['cases']:assert hashes[case['label']]==case['input_sha256']
    for path,sha in build['sources'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
    assert hashes['bank']=='d9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0'
    assert hashes['refs']=='78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    receipt=EVIDENCE/'deploy60-revisits-v1/receipts/0afb2dfe-42c4-43f7-84eb-0d5d29dfd6cb.json'
    plan,profile=g.deployment_identity(receipt,serial=ENDPOINT[0],host=ENDPOINT[1])
    authority=LocalCaptureAuthority(Path('/srv/bulk/leo/control'),(RadioResource('radio_pluto_5d4d',ENDPOINT[0],'ip:'+ENDPOINT[1]),))
    remote='/tmp/paced-acquisition-'+uuid.uuid4().hex
    evidence=dict(scope='paced_saved_IQ_acquisition_observer_ARM',new_rf_samples=0,native_jobs=0,
        status='started',serial=ENDPOINT[0],host=ENDPOINT[1],payload_sha256=hashes,remote_directory=remote,cases=[])
    ssh=['sshpass','-f',str(PASSWORD),'ssh','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(EVIDENCE/'radio20.known_hosts'),'-o','ConnectTimeout=5','root@'+ENDPOINT[1]]
    def run(command,data=None):return subprocess.run([*ssh,command],input=data,capture_output=True,timeout=45)
    def save():(output/'operator.json').write_text(json.dumps(evidence,indent=2)+'\n')
    try:lease=authority.claim(('radio_pluto_5d4d',),task_id='paced-acquisition-arm-v2',task_kind=CaptureTaskKind.QUALIFICATION)
    except BaseException as error:
        evidence.update(status='admission_refused',error=str(error));save();raise
    with lease,acquire_radio_lock(ENDPOINT[0]):
        transport=b.BoundSshBootstrapTransport(interface=None,host=ENDPOINT[1],password=PASSWORD.read_text().strip(),known_hosts_file=EVIDENCE/'radio20.known_hosts')
        terminal=False;directories=[];names=['worker.jsonl','worker.iq.ci16','observer.jsonl','observer.iq.ci16','stdout.json']
        try:
            evidence['before']=g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],host=ENDPOINT[1],layout=profile.return_iio_layout)
            run('mkdir '+shlex.quote(remote)).check_returncode()
            for name,data in payload.items():
                run('cat > '+shlex.quote(remote+'/'+name),data).check_returncode()
                check=run('sha256sum '+shlex.quote(remote+'/'+name));check.check_returncode();assert check.stdout.decode().split()[0]==hashes[name]
            run('chmod 700 '+shlex.quote(remote+'/probe')).check_returncode();save()
            for label,cut in [('positive',0),('positive',3),('control',0)]:
                name=f'{label}-{cut}';directory=remote+'/'+name;directories.append(directory)
                run('mkdir '+shlex.quote(directory)).check_returncode()
                result=run(shlex.join([remote+'/probe',remote+'/'+label,remote+'/bank',remote+'/refs',str(cut),directory])+' > '+shlex.quote(directory+'/stdout.json'))
                evidence['cases'].append(dict(label=label,cut=cut,exit_code=result.returncode,stderr=result.stderr.decode()));save();result.check_returncode()
                archive=run('tar -C '+shlex.quote(remote)+' -cf - '+shlex.quote(name));archive.check_returncode()
                with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
                    assert {m.name.rstrip('/') for m in tar.getmembers()}=={name,*(name+'/'+n for n in names)}
                    tar.extractall(output,filter='data')
                row=json.loads((output/name/'stdout.json').read_text());evidence['cases'][-1]['summary']=row
                evidence['cases'][-1]['sha256']={n:hashlib.sha256((output/name/n).read_bytes()).hexdigest() for n in names}
                save();print(row,flush=True)
            terminal=True;evidence['status']='complete_review_pending'
            manifest=dict(cases=[dict(label=c['label'],input_sha256=hashes[c['label']],**c['summary']) for c in evidence['cases']])
            (output/'result.json').write_text(json.dumps(manifest,indent=2)+'\n')
        except BaseException as error:
            evidence.update(status='failed',error=f'{type(error).__name__}: {error}');raise
        finally:
            try:
                evidence['after']=g.attest_tx_safe_idle(transport,plan,serial=ENDPOINT[0],host=ENDPOINT[1],layout=profile.return_iio_layout)
                if 'before' in evidence:assert evidence['before']==evidence['after']
                if terminal:
                    paths=[remote+'/'+k for k in payload]+[d+'/'+n for d in directories for n in names]
                    run('rm -f '+shlex.join(paths)+' && rmdir '+shlex.join([*directories,remote])).check_returncode();evidence['temporary_files_removed']=True
            finally:save()
    print(evidence['status'],flush=True)

if __name__=='__main__':main()
