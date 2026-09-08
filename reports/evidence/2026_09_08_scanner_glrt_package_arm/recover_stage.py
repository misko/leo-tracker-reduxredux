"""Resolve the known task-created, failed initial stage before a fresh attempt.

The original fixed mkdir succeeded, all eight files uploaded, and then stat was
unavailable. That operation left only this exact build's directory plus an
empty, receipt-named scratch. Revalidate hashes/identity/idle before removal.
"""
from pathlib import Path
import os
import re
import shutil
import json

from lan_access import call, password as default_password
from pluto_plus.inventory import scan_local_usb_plutos
from pluto_plus.radio_lock import acquire_radio_lock
from pluto_plus.userspace_iiod import PinnedPasswordSshIiodTransport
from pluto_plus.userspace_iiod_bundle import load_iiod_companion_bundle

root = Path(__file__).resolve().parent
bundle = load_iiod_companion_bundle(Path('/tmp/leo-glrt-userspace-bundle.CS9kKMOf/release/bundle.json'))
previous = json.loads((root/'end.json').read_bytes())
assert previous['daemon_retained'] is False and previous['bundle_retained'] is True
scratch = previous['scratch_retained']
assert scratch == '/tmp/leo-package-check.SC45Lx'
assert bundle.remote_directory == '/tmp/ppu-iiod-bundle-0f8e84999ab145a595c829886af5ca31'
credentials = root/'recovery-credentials'
credentials.mkdir(mode=0o700)
known, secret = credentials/'known_hosts', credentials/'password'
shutil.copyfile('/tmp/leo-presence-holdout.8JIL7Y/known_hosts',known)
known.chmod(0o600)
fd = os.open(secret, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
try:
    os.write(fd,(default_password+'\n').encode())
finally:
    os.close(fd)
serial = 'winbond-db620818a328172c'
transport = PinnedPasswordSshIiodTransport(host='192.168.1.14',expected_serial=serial,
    known_hosts_file=known,password_file=secret)
try:
    with acquire_radio_lock(serial):
        devices = [d for d in scan_local_usb_plutos() if d.serial == serial]
        assert len(devices) == 1 and devices[0].usb_path == '/sys/bus/usb/devices/5-1'
        assert transport.attest_radio_serial() == serial
        status = call('cat /sys/bus/iio/devices/iio:device*/buffer/enable\nnetstat -nt\nps')
        assert status.returncode == 0
        lines = status.stdout.splitlines()
        assert lines[:2] == ['0','0']
        assert all(':22 ' in line and '192.168.1.142:' in line for line in lines if line.startswith('tcp'))
        assert not any('/tmp/' in line for line in lines)
        result = call(f'cat {bundle.remote_directory}/owner')
        assert result.returncode == 0 and re.fullmatch(r'[0-9a-f]{32}\n',result.stdout)
        owner = result.stdout.strip()
        transport.verify_companions(bundle,owner)
        transport.cleanup_companions(bundle,owner)
        # rmdir cannot erase a nonempty directory; no recursive fallback.
        result = call(f'test ! -L {scratch} && rmdir {scratch}')
        assert result.returncode == 0, result.stderr
        check = call(f'test ! -e {bundle.remote_directory} && test ! -e {scratch}')
        assert check.returncode == 0
        receipt = dict(verified=True,scope='Recovery of known task-created failed stage',
            initial_ownership_token_was_not_persisted=True,
            ownership_basis='Exclusive mkdir succeeded in retained initial attempt; exact release path, complete hashes/inventory and idle target revalidated',
            observed_owner=owner,manifest_sha256=bundle.manifest_sha256,
            removed_companion_directory=bundle.remote_directory,removed_empty_scratch=scratch,
            original_release_retained=True,radio_state_before=status.stdout)
        with (root/'recovery.json').open('x') as stream:
            json.dump(receipt,stream,indent=2)
            stream.write('\n')
        print('Verified failed-stage payloads and removed only their known temporary copies; originals retained.')
finally:
    secret.unlink()
    known.unlink()
    credentials.rmdir()
