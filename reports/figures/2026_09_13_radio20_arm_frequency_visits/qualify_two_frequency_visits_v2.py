"""One serial-bound ARM-local pair of <=10.067-second upper-edge visits."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import uuid

sys.path.insert(0,'/home/mouse9911/gits/plutosdr-fw-radio20-tracking/scripts')
import qualify_glrt_cpu_live20 as live

E=live.EVIDENCE


def main():
    if len(sys.argv)!=3: raise SystemExit('usage: qualify_two_frequency_visits.py NEW_OUTPUT DEPLOYMENT_RECEIPT')
    out=Path(sys.argv[1]);deployment=Path(sys.argv[2])
    plan,profile=live.g.deployment_identity(deployment,serial=live.ENDPOINT[0],host=live.ENDPOINT[1])
    rate=60000000
    assert plan['expected_firmware']==f'glrt-iq-tracking-r{rate}-v1'
    payload={'probe':(E/'glrt-cpu-visit-probe-v2').read_bytes(),
             'bank':(E/'coarse-bank.ci16').read_bytes(),'references':(E/'direct-references.ci16').read_bytes()}
    hashes={k:hashlib.sha256(v).hexdigest() for k,v in payload.items()}
    assert hashes['bank']=='d9f3452e45180c560a200bb76c9bfe2d7c46b17560fd46495ea74c50f50547f0'
    assert hashes['references']=='78b50e1aea5c350889b0798fc691491299925932e496a918cd5fbd3b9bc4faf2'
    out.mkdir(exist_ok=False)
    receipt={'scope':'bounded_ARM_two_frequency_visits','status':'started','rate':rate,
        'serial':live.ENDPOINT[0],'lo_plan_hz':[1690312500,1940312500],
        'rf_sample_limit':50331648,'rf_duration_limit_s':50331648/2500000,
        'payload_sha256':hashes,'native_tracking_qualified':False,'artifacts':{}}
    save=lambda:(out/'operator.json').write_text(json.dumps(receipt,indent=2)+'\n')
    authority=live.LocalCaptureAuthority(Path('/srv/bulk/leo/control'),(
        live.RadioResource('radio_pluto_5d4d',live.ENDPOINT[0],'ip:'+live.ENDPOINT[1]),))
    try: lease=authority.claim(('radio_pluto_5d4d',),task_id='two-frequency20-'+out.name,task_kind=live.CaptureTaskKind.QUALIFICATION)
    except Exception as error:
        receipt.update(status='admission_refused',error=str(error),rf_samples_collected=0);save();raise
    remote='/tmp/gli-two-visits-'+uuid.uuid4().hex
    receipt['remote_directory']=remote
    ssh=['sshpass','-f',str(live.PASSWORD),'ssh','-o','StrictHostKeyChecking=yes','-o',
         'UserKnownHostsFile='+str(E/'radio20.known_hosts'),'-o','ConnectTimeout=5','root@'+live.ENDPOINT[1]]
    def run(command,data=None,timeout=45): return subprocess.run([*ssh,command],input=data,capture_output=True,timeout=timeout)
    names=['visits.txt']+[f'visit-{n}/{f}' for n in range(2) for f in (*live.ARTIFACTS,'stdout.json','stderr.txt')]
    with lease,live.acquire_radio_lock(live.ENDPOINT[0]):
        transport=live.b.BoundSshBootstrapTransport(interface=None,host=live.ENDPOINT[1],
            password=live.PASSWORD.read_text().strip(),known_hosts_file=E/'radio20.known_hosts')
        mounted=started=terminal=retrieved=False
        try:
            receipt['before']=live.g.attest_tx_safe_idle(transport,plan,serial=live.ENDPOINT[0],host=live.ENDPOINT[1],layout=profile.return_iio_layout)
            memory=run('cat /proc/meminfo');memory.check_returncode()
            available=int(re.search(r'^MemAvailable:\s+(\d+) kB$',memory.stdout.decode(),re.M)[1])
            # 192 MiB raw IQ + <=48 MB worker IQ + 16 MiB native journals +
            # 5.28 MB observer IQ + grids/metadata fit a 280-MiB evidence allowance.
            receipt['memory']={'available_kib':available,'required_kib':360*1024,'evidence_kib':280*1024}
            assert available>=360*1024
            run('mkdir '+shlex.quote(remote)).check_returncode()
            run('mount -t tmpfs -o size=352m,nosuid,nodev tmpfs '+shlex.quote(remote)).check_returncode();mounted=True
            df=run('df -Pk '+shlex.quote(remote));df.check_returncode()
            fields=df.stdout.decode().splitlines()[1].split()
            assert fields[0]=='tmpfs' and fields[-1]==remote and int(fields[3])>=320*1024
            receipt['filesystem']=df.stdout.decode()
            import iio
            ctx=iio.Context('ip:'+live.ENDPOINT[1])
            try:
                assert ctx.attrs['hw_serial']==live.ENDPOINT[0] and ctx.attrs['fw_version']==plan['expected_firmware']
                receipt['configured']=live.configure_idle_rx(ctx,rate=rate,lo_hz=1690312500,evidence=receipt,
                    memory_info=memory.stdout.decode(),blocks=1536)
                receipt['calibration']={};live.g.calibrate_rx(ctx.find_device('ad9361-phy'),source_rate=rate,evidence=receipt['calibration'])
            finally: live._close_iio_context(iio,ctx)
            for name,data in payload.items():
                run('cat > '+shlex.quote(remote+'/'+name),data).check_returncode()
                got=run('sha256sum '+shlex.quote(remote+'/'+name));got.check_returncode()
                assert got.stdout.decode().split()[0]==hashes[name]
            run('chmod 700 '+shlex.quote(remote+'/probe')).check_returncode()
            save();print(json.dumps({'phase':'starting_ARM_two_visits','rf_limit_s':receipt['rf_duration_limit_s']}),flush=True)
            started=True
            result=run(shlex.join([remote+'/probe',str(rate),live.ENDPOINT[0],remote+'/bank',remote+'/references',remote,
                                  *map(str,receipt['lo_plan_hz'])]),timeout=70)
            terminal=True;receipt['exit_code']=result.returncode
            (out/'stdout.json').write_bytes(result.stdout);(out/'stderr.txt').write_bytes(result.stderr)
            for name in names:
                exists=run('test -f '+shlex.quote(remote+'/'+name))
                if exists.returncode==1: receipt['artifacts'][name]=None;continue
                exists.check_returncode();data=run('cat '+shlex.quote(remote+'/'+name));data.check_returncode()
                target=out/name;target.parent.mkdir(exist_ok=True);target.write_bytes(data.stdout)
                receipt['artifacts'][name]={'bytes':len(data.stdout),'sha256':hashlib.sha256(data.stdout).hexdigest()}
            retrieved=True
            ctx=iio.Context('ip:'+live.ENDPOINT[1])
            try:
                assert ctx.attrs['hw_serial']==live.ENDPOINT[0] and ctx.attrs['fw_version']==plan['expected_firmware']
                receipt['rf_after']=live.g.rf_state(ctx.find_device('ad9361-phy'))
                original=dict(receipt['configured']['rf_state']);after=dict(receipt['rf_after'])
                actual_lo=int(after.pop('rx_lo'));original.pop('rx_lo')
                assert original==after
                if result.returncode==0: assert abs(actual_lo-receipt['lo_plan_hz'][-1])<=16
            finally: live._close_iio_context(iio,ctx)
            result.check_returncode();assert all(v is not None for v in receipt['artifacts'].values())
            receipt['status']='complete_review_pending'
        except BaseException as error:
            receipt.update(status='failed',error=f'{type(error).__name__}: {error}');raise
        finally:
            try:
                receipt['after']=live.g.attest_tx_safe_idle(transport,plan,serial=live.ENDPOINT[0],host=live.ENDPOINT[1],layout=profile.return_iio_layout)
                if mounted and (not started or (terminal and retrieved)):
                    run('rm -f '+shlex.join([remote+'/'+n for n in (*payload,*names)])).check_returncode()
                    for n in range(2):
                        directory=remote+f'/visit-{n}'
                        exists=run('test -d '+shlex.quote(directory))
                        if exists.returncode==0: run('rmdir '+shlex.quote(directory)).check_returncode()
                        else: assert exists.returncode==1
                    run('umount '+shlex.quote(remote)).check_returncode();run('rmdir '+shlex.quote(remote)).check_returncode()
                    receipt['temporary_files_removed']=True
            finally: save()
    print(json.dumps({'status':receipt['status'],'output':str(out)}),flush=True)


if __name__=='__main__': main()
