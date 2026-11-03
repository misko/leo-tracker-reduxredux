"""Activate a canary-verified runtime only while the ALGO03 watcher is idle."""

import argparse
import json
import os
import select
import signal
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from algo03_runtime_release import verify

SERVICE = 'leo-algo03-graph-position.service'
OVERRIDE = Path(
    '/etc/systemd/system/leo-algo03-graph-position.service.d/95-runtime-composition.conf')


def activity(pid, proc=Path('/proc')):
    root = proc/str(pid)
    children = sorted({int(x) for p in (root/'task').glob('*/children')
                       for x in p.read_text().split()})
    owners = []
    for p in (root/'fd').iterdir():
        try:
            target = Path(os.readlink(p))
        except FileNotFoundError:
            continue
        if target.name == 'owner.lock':
            owners.append(str(target))
    watcher = [p for p in owners if Path(p).parent.name == 'watcher']
    jobs = [p for p in owners if p not in watcher]
    return dict(pid=pid, children=children, job_owner_files=jobs,
                watcher_owner_files=watcher, idle=not children and not jobs and len(watcher) == 1)


def main_pid():
    return int(subprocess.check_output(
        ['systemctl', 'show', SERVICE, '--property=MainPID', '--value'], text=True))


def activate(stage, parity, template, *, execute=False):
    root, pin = Path(stage['release']), stage['runtime_manifest_sha256']
    if not root.is_relative_to('/opt/leo-fast-graph-runtime-algo03'):
        raise ValueError('Unexpected runtime root')
    if not (parity['passed'] and parity['tolerance'] == 0 and parity['exact_leaves'] > 0
            and parity['both_calibration_arms_required']
            and parity['candidate_runtime_manifest_sha256'] == pin):
        raise ValueError('Exact installed canary required')
    verify(root, pin)
    rendered = template.replace('@RUNTIME_ROOT@', str(root)).replace('@RUNTIME_SHA256@', pin)
    if '@' in rendered or 'LEO_ALGO03_RUNTIME_MANIFEST_SHA256='+pin not in rendered:
        raise ValueError('Unrendered or incomplete runtime configuration')
    pid = main_pid()
    before = activity(pid)
    if not before['idle'] or not execute:
        return dict(activated=False, before=before, dry_run=not execute)
    if OVERRIDE.exists():
        raise FileExistsError('Preserve existing override before another activation')
    handle = os.pidfd_open(pid)
    installed = False
    try:
        signal.pidfd_send_signal(handle, signal.SIGSTOP)
        for _ in range(100):
            states = [p.read_text().split(') ', 1)[1].split()[0]
                      for p in Path(f'/proc/{pid}/task').glob('*/stat')]
            if states and all(s == 'T' for s in states):
                break
            time.sleep(.01)
        else:
            raise RuntimeError('Watcher did not fully stop for idle verification')
        frozen = activity(pid)
        if main_pid() != pid or not frozen['idle']:
            return dict(activated=False, before=before, frozen=frozen)
        verify(root, pin)
        OVERRIDE.parent.mkdir(parents=True, exist_ok=True)
        with OVERRIDE.open('x') as stream:
            stream.write(rendered)
        installed = True
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        signal.pidfd_send_signal(handle, signal.SIGTERM)
        signal.pidfd_send_signal(handle, signal.SIGCONT)
        if not select.select([handle], [], [], 10)[0]:
            raise RuntimeError('Idle watcher did not exit')
        # start is idempotent; unlike restart it cannot kill a replacement worker.
        subprocess.run(['systemctl', 'start', SERVICE], check=True)
        current = main_pid()
        if current == pid or not current:
            raise RuntimeError('Replacement watcher did not start')
        return dict(activated=True, before=before, frozen=frozen, new_pid=current,
                    runtime=str(root), runtime_manifest_sha256=pin,
                    override=str(OVERRIDE), activated_utc_ns=time.time_ns())
    finally:
        with suppress(ProcessLookupError):
            signal.pidfd_send_signal(handle, signal.SIGCONT)
        os.close(handle)
        if installed:
            print(json.dumps(dict(override_installed=str(OVERRIDE))), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('stage', 'canary-parity', 'template', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--execute', action='store_true')
    p.add_argument('--wait-seconds', type=int, choices=range(0, 1801), default=0)
    a = p.parse_args()
    if not a.output.resolve().is_relative_to('/srv/bulk/leo/research') or a.output.exists():
        raise ValueError('New private activation receipt required')
    stage = json.loads(a.stage.read_text())
    parity = json.loads(a.canary_parity.read_text())
    template = a.template.read_text()
    deadline = time.monotonic()+a.wait_seconds
    while True:
        result = activate(stage, parity, template, execute=a.execute)
        if result['activated'] or not a.execute or time.monotonic() >= deadline:
            break
        time.sleep(2)
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))
