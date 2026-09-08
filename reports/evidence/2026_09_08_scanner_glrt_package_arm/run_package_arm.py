"""Bounded target loader + saved-IQ checks; never starts an iiOD listener or RF.

Production pinned companion staging/cleanup is exercised on the exact USB spare.
The daemon is invoked only with -V, whose checked branch exits before IIO context
creation. The SDK replay has no IIO dependency and uses modeled input arrivals.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
import shutil
import time
import uuid

from lan_access import call, transfer, password as default_password
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.userspace_iiod import PinnedPasswordSshIiodTransport, RemoteIiodPaths
from pluto_plus.userspace_iiod_bundle import load_iiod_companion_bundle
from tools.qualify_native_presence import digest, write_json
from tools.qualify_scanner_glrt_sdk import build, verify

root = Path(__file__).resolve().parent
release = Path('/tmp/leo-glrt-userspace-bundle.CS9kKMOf/release')
bundle = load_iiod_companion_bundle(release/'bundle.json')
artifact = json.loads((release.parent/'receipt.json').read_bytes())
algorithm, configuration = artifact['algorithm_sha256'], artifact['configuration_sha256']
assert bundle.manifest_sha256 == '01c6c1b7037a7dd3de700ff78fd7c9e779373f2d2e4d4ee26d26256851407e7b'
assert digest(release/'iiod') == bundle.daemon_sha256
compiler = '/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc'
parent = build(root/'parent', compiler=compiler,
               cflags=('-mcpu=cortex-a9', '-mfpu=neon', '-mfloat-abi=hard'),
               sdk_library=release/'libleo-scanner-glrt.so',
               runtime_rpath=Path(bundle.remote_directory))
assets = Path('/tmp/leo-presence-holdout.8JIL7Y/arm')
previous = Path('/tmp/leo-presence-arm-profile.UuBXXp/replay-300s')
packs, references = {}, {}
for rate in (2500000, 5000000):
    packs[rate] = assets/f'{rate}.pack'
    references[rate] = json.loads((previous/f'{rate}-combined.manifest.json').read_bytes())
    assert digest(packs[rate]) == references[rate]['pack_sha256']
    assert digest(release/f'templates-{rate}.bin') == references[rate]['templates_sha256']
payload = {'sdk-replay': parent, **{f'{rate}.pack': path for rate, path in packs.items()}}
payload_hashes = {name: digest(path) for name, path in payload.items()}
serial, host = 'winbond-db620818a328172c', '192.168.1.14'
session = uuid.uuid4().hex
paths = RemoteIiodPaths(*(f'/tmp/ppu-iiod-{session}.{suffix}' for suffix in ('bin','pid','log')))
order = [(2500000, True, 1936), (5000000, True, 1936),
         (2500000, False, 15000), (5000000, False, 15000)]
freeze = dict(recipe_sha256=digest(Path(__file__)), manifest_sha256=bundle.manifest_sha256,
              algorithm_sha256=algorithm, configuration_sha256=configuration, order=order,
              host=host, serial=serial, daemon_mode='-V only; no context/listener',
              payload_hashes=payload_hashes, live_rf=False, changed_firmware=False,
              model='Repeated saved RX1, synthetic RX0/1ms guard, 131072-sample blocks, 2-block-late metadata, 40ms burst delay',
              budget='Two 1.936s loader-traced and two 15s untraced replays; no retries',
              gate='Every preceding startup/numerical/load-path check must pass')
write_json(root/'freeze.json', freeze)
credentials = root/'credentials'
credentials.mkdir(mode=0o700)
known = credentials/'known_hosts'
shutil.copyfile('/tmp/leo-presence-holdout.8JIL7Y/known_hosts', known)
known.chmod(0o600)
secret = credentials/'password'
fd = os.open(secret, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
try:
    os.write(fd, (default_password+'\n').encode())
finally:
    os.close(fd)
transport = PinnedPasswordSshIiodTransport(host=host, expected_serial=serial,
                                         known_hosts_file=known, password_file=secret)
scratch = None
daemon = None
bundle_attempted = False
cleanup_errors = []
summaries = []

def recorded(label, command, timeout=15):
    result = call(command, timeout=timeout)
    write_json(root/f'{label}.json', dict(command=command, returncode=result.returncode,
                                        stdout=result.stdout, stderr=result.stderr))
    if result.returncode:
        raise RuntimeError(f'{label}: {result.returncode}: {result.stderr[-1000:]}')
    return result.stdout

def idle(label):
    devices = [d for d in scan_local_usb_plutos() if d.serial == serial]
    assert len(devices) == 1 and devices[0].usb_path == '/sys/bus/usb/devices/5-1'
    assert transport.attest_radio_serial() == serial
    assert recorded(label+'-mac','cat /sys/class/net/eth0/address').strip() == '7e:09:12:85:cf:8e'
    assert '192.168.1.14/' in recorded(label+'-eth0','ip -4 addr show dev eth0')
    assert recorded(label+'-buffers','cat /sys/bus/iio/devices/iio:device*/buffer/enable').split() == ['0','0']
    network = recorded(label+'-network','netstat -nt')
    assert all(':22 ' in line and '192.168.1.142:' in line
               for line in network.splitlines() if line.startswith('tcp'))
    processes = recorded(label+'-processes','ps')
    assert not any('/tmp/' in line and ('sdk-replay' in line or '/worker' in line or 'ppu-iiod-' in line)
                   for line in processes.splitlines())
    stats = recorded(label+'-resources','cat /proc/loadavg\ncat /proc/meminfo\ndf -Pk /tmp')
    return [d.model_dump(mode='json') for d in devices], stats

def system_hashes(label):
    return recorded(label, 'sha256sum /usr/sbin/iiod /usr/lib/libfftw3.so.3 /lib/libc.so.6 '
                    '/lib/libm.so.6 /lib/libpthread.so.0 /lib/librt.so.1 /lib/libdl.so.2 '
                    '/lib/ld-linux-armhf.so.3')

def verify_payload(label):
    output = recorded(label, 'sha256sum '+ ' '.join(shlex.quote(f'{scratch}/{name}') for name in payload))
    assert {Path(line.split()[1]).name: line.split()[0] for line in output.splitlines()} == payload_hashes

def trace_libraries(stderr, names):
    initialized = re.findall(r'calling init:\s+(\S+)', stderr)
    for name in names:
        matches = [path for path in initialized if Path(path).name == name]
        assert matches and set(matches) == {f'{bundle.remote_directory}/{name}'}, (name,matches)
    assert 'cannot open' not in stderr and 'error:' not in stderr and 'SDK startup rejected' not in stderr
    return sorted(set(initialized))

try:
    with acquire_radio_lock(serial):
        try:
            usb, resources = idle('preflight')
            write_json(root/'usb-identity.json', usb)
            before_system = system_hashes('system-before')
            # A test-specific scratch is separate from the immutable release inventory.
            scratch = recorded('scratch','mktemp -d /tmp/leo-package-check.XXXXXX').strip()
            assert re.fullmatch(r'/tmp/leo-package-check\.[A-Za-z0-9]{6}', scratch)
            daemon = transport.stage(paths, (release/'iiod').read_bytes(), expected_sha256=bundle.daemon_sha256)
            bundle_attempted = True
            transport.stage_companions(bundle, session)
            transport.verify_companions(bundle, session)
            write_json(root/'stage.json', dict(daemon=dict(path=daemon.path,bytes=daemon.bytes,sha256=daemon.sha256),
                companion_manifest_sha256=bundle.manifest_sha256, remote_directory=bundle.remote_directory,
                companions=len(bundle.files), session=session))
            # LD_DEBUG is process-local diagnostics, never LD_LIBRARY_PATH or an installed override.
            version = call(f'LD_DEBUG=libs {paths.binary} -V',timeout=15)
            write_json(root/'daemon-version.json', dict(returncode=version.returncode,stdout=version.stdout,stderr=version.stderr))
            assert version.returncode == 0 and version.stdout.strip() == '0.25'
            loaded = trace_libraries(version.stderr, ['libleo-scanner-glrt.so','libiio.so.0','libxml2.so.2','libz.so.1'])
            write_json(root/'daemon-loader.json',dict(verified=True,initialized=loaded,no_iio_context_or_listener=True))
            for name,path in payload.items():
                result = transfer([path],f'{scratch}/{name}')
                write_json(root/f'transfer-{name}.json',dict(returncode=result.returncode,stderr=result.stderr,sha256=payload_hashes[name]))
                assert result.returncode == 0
            recorded('parent-mode',f'chmod 700 {scratch}/sdk-replay')
            verify_payload('payload-initial')
            for index,(rate,traced,duration) in enumerate(order):
                idle(f'before-{index}')
                label = f'{index}-{rate}-trace{int(traced)}'
                command = (('LD_DEBUG=libs ' if traced else '') + f'nice -n 10 {scratch}/sdk-replay '
                           f'{bundle.remote_directory}/worker {bundle.remote_directory}/templates-{rate}.bin '
                           f'{scratch}/{rate}.pack {duration} 2 40 1 {algorithm} {configuration}')
                print(f'Starting {label}: {duration/1000:g}s saved-IQ packaged-SDK check',flush=True)
                began = time.monotonic()
                result = call(command,timeout=duration/1000+30)
                write_json(root/f'{label}.execution.json', dict(command=command,returncode=result.returncode,
                           stderr=result.stderr,elapsed_s=time.monotonic()-began))
                with (root/f'{label}.jsonl').open('x') as stream:
                    stream.write(result.stdout)
                assert result.returncode == 0, result.stderr[-1000:]
                loaded = trace_libraries(result.stderr,['libleo-scanner-glrt.so','libfftw3.so.3']) if traced else []
                if not traced:
                    assert not result.stderr
                checked = verify(result.stdout,references[rate],duration,delay_blocks=2,jitter_ms=40,enabled=True,
                                 algorithm_sha256=algorithm,configuration_sha256=configuration)
                checked.update(raw_sha256=digest(root/f'{label}.jsonl'),traced=traced,loaded_libraries=loaded)
                write_json(root/f'{label}.verification.json',checked)
                summaries.append(dict(label=label,**checked))
                print(json.dumps({k:checked[k] for k in ('verified','results','callback_wall_ms','worker_wall_ms')}),flush=True)
            idle('postflight')
            verify_payload('payload-final')
            transport.verify_companions(bundle,session)
            assert before_system == system_hashes('system-after')
            assert {name:digest(path) for name,path in payload.items()} == payload_hashes
            write_json(root/'summary.json',dict(runs=summaries,system_libraries_unchanged=True,
                       live_rf=False,goal_complete=False,iiod_listener_started=False))
        finally:
            # No background remote command is launched. A timeout does not prove
            # the foreground child stopped; inspect and retain if its path remains.
            try:
                idle('cleanup-precondition')
            except BaseException as error:
                cleanup_errors.append(f'cannot prove idle: {error}')
            if not cleanup_errors:
                if daemon is not None:
                    try:
                        transport.cleanup(paths,daemon)
                        daemon = None
                    except BaseException as error:
                        cleanup_errors.append(f'daemon: {error}')
                if bundle_attempted:
                    try:
                        transport.cleanup_companions(bundle,session)
                        bundle_attempted = False
                    except BaseException as error:
                        cleanup_errors.append(f'companions: {error}')
                if scratch is not None:
                    try:
                        verify_payload('cleanup-payload')
                        recorded('cleanup-files','rm '+ ' '.join(shlex.quote(f'{scratch}/{name}') for name in payload))
                        recorded('cleanup-directory','rmdir '+shlex.quote(scratch))
                        scratch = None
                    except BaseException as error:
                        cleanup_errors.append(f'scratch: {error}')
finally:
    # Derived, session-private host credential files only; no public key source is removed.
    secret.unlink()
    known.unlink()
    credentials.rmdir()
    write_json(root/'end.json',dict(scratch_retained=scratch,daemon_retained=daemon is not None,
               bundle_retained=bundle_attempted,cleanup_errors=cleanup_errors,credentials_removed=True,
               recipe_unchanged=digest(Path(__file__))==freeze['recipe_sha256']))
assert len(summaries)==4 and not cleanup_errors
print('All four saved-IQ package checks verified; temporary target files removed.',flush=True)
