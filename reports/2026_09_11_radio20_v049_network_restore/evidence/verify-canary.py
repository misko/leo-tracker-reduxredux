from dataclasses import asdict
from functools import partial
import json
import os
from pathlib import Path
import re
import subprocess

from leo.acquisition import CaptureTaskKind, LocalCaptureAuthority, RadioResource
from leo.cli.persistent_hop_canary import PersistentHopCanarySettings, run_persistent_hop_canary
from leo.storage.persistent_hop_capture import capture_persistent_hop_to_store
from pluto_plus.hardware.iio import IioRadioDevice
from pluto_plus.models import GainMode
from pluto_plus.userspace_iiod import UserspaceIiodDeployment

root = Path('/srv/bulk/leo/qualification/deployment/radio20-v049-canary-20260911')
credentials = Path(os.environ['CREDENTIALS_DIRECTORY'])
serial = '1040005e0b100007100010000bf33a5d4d'
radio_id = 'radio_pluto_5d4d'
session_id = 'canary-hop-20260911T175000Z-5m-v049-network'
runtime = Path('/opt/leo-tracker/releases/d9b1e6dd486918cf8bd8876870cfabc0ceab11f6/runtime/scanner-glrt')
authority = LocalCaptureAuthority(Path('/srv/bulk/leo/control'), (
    RadioResource(radio_id, serial, 'ip:192.168.1.20'),
))
with authority.claim((radio_id,), task_id=session_id, task_kind=CaptureTaskKind.SCANNER_SWEEP):
    radio = IioRadioDevice('ip:192.168.1.20', serial=serial)
    radio.open()
    try:
        before = radio.read_settings()
        target = before.model_copy(update={'channels': (0, 1), 'gain_mode': GainMode.MANUAL, 'gain_db': 40.0})
        after = radio.apply_settings(target)
        assert after.gain_mode is GainMode.MANUAL and after.gain_db == 40.0
        (root / 'manual-gain-baseline.json').write_text(json.dumps({
            'before': before.model_dump(mode='json'), 'after': after.model_dump(mode='json'),
            'reason': 'Establish the configured scanner manual-gain baseline before capture snapshots.',
        }, indent=2))
        print('Configured paired RX manual 40 dB; no receive buffer opened yet.', flush=True)
    finally:
        radio.close()
    lifecycle = UserspaceIiodDeployment(
        host='192.168.1.20', expected_serial=serial,
        binary_path=runtime / 'iiod', bundle_manifest_path=runtime / 'bundle.json',
        known_hosts_path=credentials / 'scanner-iiod-ssh-known-hosts',
        password_path=credentials / 'scanner-iiod-ssh-password',
    )
    start = lifecycle.enter_and_attest()
    (root / 'lifecycle-start.json').write_text(json.dumps(asdict(start), indent=2))
    print('Scanner endpoint attested; starting one 300-second 5 MS/s canary.', flush=True)
    cleaned = False
    def cleanup():
        global cleaned
        if cleaned:
            return
        cleaned = True
        log = asdict(start)['paths']['log']
        assert re.fullmatch(r'/tmp/ppu-iiod-[0-9a-f]{32}\.log', log)
        command = ['sshpass', '-f', str(credentials / 'scanner-iiod-ssh-password'),
                   'ssh', '-o', 'StrictHostKeyChecking=yes', '-o',
                   f'UserKnownHostsFile={credentials / "scanner-iiod-ssh-known-hosts"}',
                   '-o', 'ConnectTimeout=8', 'root@192.168.1.20', f'cat {log}']
        try:
            result = subprocess.run(command, capture_output=True, timeout=15)
            (root / 'iiod.log').write_bytes(result.stdout)
        finally:
            stop = lifecycle.exit_and_verify()
            (root / 'lifecycle-stop.json').write_text(json.dumps(asdict(stop), indent=2))
    try:
        result = run_persistent_hop_canary(PersistentHopCanarySettings(
            host='192.168.1.20', expected_serial=serial, radio_id=radio_id,
            bulk_root=Path('/srv/bulk/leo'), sample_rate_hz=5_000_000,
            session_id=session_id, iiod_port=30432,
        ), capture=partial(capture_persistent_hop_to_store, before_publish=cleanup))
        (root / 'canary.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result), flush=True)
    finally:
        cleanup()
