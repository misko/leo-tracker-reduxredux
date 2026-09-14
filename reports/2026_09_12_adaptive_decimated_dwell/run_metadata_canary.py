"""One bounded, authorized baseline canary; restore scheduled service on exit."""

import hashlib
import json
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from urllib.request import urlopen

from leo.cli.composition import CliSettings, LocalAcquisitionBackend
from leo.scanner.single_rx import SINGLE_RX_PROFILE_ID
from leo.storage.persistent_hop import PersistentHopIqStore


def main():
    output = Path('/var/tmp/leo-metadata-canary-20260912-02.json')
    bulk = Path('/srv/bulk/leo-metadata-canary-20260912-02')
    candidate = Path('/var/tmp/leo-queued-metadata-builds/candidate-clean')
    if output.exists() or bulk.exists():
        raise FileExistsError('canary is single-use; retain existing evidence')
    with urlopen('http://192.168.1.142:8090/api/v1/acquisition-queue', timeout=10) as stream:
        queue = json.load(stream)
    if queue['truncated'] or any(item['state'] == 'leased' for item in queue['items']):
        raise RuntimeError('an acquisition is active or queue state is incomplete')
    subprocess.run(['systemctl', 'is-active', '--quiet', 'leo-acquisition.service'], check=True)
    provenance = json.loads((candidate / 'provenance.json').read_text())
    digest = hashlib.sha256((candidate / 'iiod').read_bytes()).hexdigest()
    assert digest == provenance['artifact']['sha256']
    assert provenance['source']['head'] == '10e72e8b3e8c4e4d62067d2d1d21ef365b6c8fcf'
    values = {}
    for path in (Path('/etc/leo/leo.env'), Path('/etc/leo/acquisition.env')):
        for line in path.read_text().splitlines():
            key, separator, value = line.partition('=')
            if separator and not line.lstrip().startswith('#'):
                values[key.strip()] = value.strip().strip('\'"')
    assert values['LEO_SCANNER_PROFILE'] == SINGLE_RX_PROFILE_ID
    values.update(
        LEO_BULK_ROOT=str(bulk),
        LEO_SCANNER_REPORT_ROOT=str(bulk / 'scanner-reports'),
        LEO_SCANNER_PERSISTENT_IIOD_BINARY_PATH=str(candidate / 'iiod'),
        CREDENTIALS_DIRECTORY='/etc/leo/credentials',
    )
    # This fixed daemon uses only existing system libraries. Source provenance
    # is verified above; it is not a PPU companion-file transport manifest.
    values.pop('LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH', None)
    settings = CliSettings.from_environ(values)
    backend = LocalAcquisitionBackend(settings)
    slot = datetime.fromtimestamp(int(time.time() // 1200) * 1200, UTC)
    intent = backend.scheduled_scanner_intent(
        operation_key=f'scheduled-scanner:{slot:%Y%m%dT%H%M%SZ}', scheduled_for=slot,
    )
    assert intent.run_duration_seconds == 300
    report = dict(
        status='prepared', started_utc_ns=time.time_ns(), maximum_rf_seconds=300,
        purpose='metadata polling margin baseline canary; no adaptive decisions',
        provider_sha256=digest, provider_revision=provenance['source']['head'],
        isolated_bulk_root=str(bulk), intent=intent.model_dump(mode='json'),
    )
    output.write_text(json.dumps(report, indent=2) + '\n')
    cancel = Event()

    def deadline(*_):
        cancel.set()
        raise TimeoutError('canary exceeded its 500-second total bound')

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(500)
    paused = False
    try:
        paused = True
        subprocess.run(['systemctl', 'stop', 'leo-acquisition.service'], check=True, timeout=30)
        report.update(status='capture_started', capture_started_utc_ns=time.time_ns())
        output.write_text(json.dumps(report, indent=2) + '\n')
        receiver = intent.configuration.receiver_ids[0]
        print(f'300s metadata canary starting on RX{receiver}', flush=True)
        result = backend.capture_scheduled_scanner(intent, cancel=cancel)
        published = PersistentHopIqStore.open_read_only(bulk).verify(result.published.session_id)
        receipt = published.manifest.receipt
        report.update(
            status='capture_finished', session_id=published.session_id,
            manifest_sha256=published.manifest_sha256,
            receipt=receipt.model_dump(mode='json'),
            timing=published.manifest.timing.model_dump(mode='json'),
            queue=published.manifest.queue_telemetry.model_dump(mode='json'),
        )
        assert receipt.qualified and receipt.capture_outcome == 'complete'
        assert receipt.continuity_attested and receipt.valid_duty_ppm >= 950000
        report['status'] = 'capture_passed'
    except BaseException as error:
        report.update(status='failed', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        signal.alarm(0)
        report['finished_utc_ns'] = time.time_ns()
        try:
            output.write_text(json.dumps(report, indent=2) + '\n')
        finally:
            if paused:
                subprocess.run(
                    ['systemctl', 'start', 'leo-acquisition.service'], check=True, timeout=30
                )
                subprocess.run(
                    ['systemctl', 'is-active', '--quiet', 'leo-acquisition.service'], check=True
                )
        print(json.dumps({k: report.get(k) for k in ('status', 'session_id', 'error')}), flush=True)


if __name__ == '__main__':
    main()
