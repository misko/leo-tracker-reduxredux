"""Activate the qualified immutable ALGO07 release; retain all prior overrides."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REVISION='7cafccaced18e6b0fa9266bd18339d61f0f9c1f4'
MODEL='algo07-causal-guarded-reassociation-v1'


def activate():
    if os.geteuid()!=0:
        raise PermissionError('Root installs immutable systemd deployment configuration')
    numerical=Path('/opt/leo-fast-graph')/REVISION
    app=Path('/opt/leo-tracker/releases')/REVISION
    if (numerical/'.incomplete').exists() or not (app/'web/dist/index.html').is_file():
        raise ValueError('Both complete immutable releases required')
    sys.path.insert(0,str(numerical/'src'))
    from leo.storage.fast_graph_position_v6 import FastGraphPositionStoreV6
    store=FastGraphPositionStoreV6('/srv/bulk/leo')
    for identifier in ('6940d22f1c98042bb2ac2de3c5665aed','1afa181f335df49bfa8906f9096f7b67'):
        status=store.status(identifier)
        if status is None or status['state']!='complete':
            raise ValueError('Installed production canary must finish before activation')
        terminal,_=store.terminal(status)
        if terminal['failure'] is not None or not (terminal.get('read_audit') or {}).get('verified'):
            raise ValueError('Installed canary must complete with a verified read audit')
    cutoff=time.time_ns()
    unit=Path('/etc/systemd/system/leo-algo07-graph-position.service')
    if unit.exists():
        raise FileExistsError('ALGO07 service already configured; inspect before replacing')
    text=(numerical/'deploy/systemd/leo-algo07-graph-position.service').read_text()
    unit.write_text(text.replace('@RELEASE@',str(numerical)).replace('@CUTOFF_UTC_NS@',str(cutoff)))
    folder=Path('/etc/systemd/system/leo-api.service.d')
    old=next(folder.glob('*-algo06.conf'))
    override=old.with_name(old.name.replace('-algo06.conf','-algo07.conf'))
    if override.exists():
        raise FileExistsError(override)
    override.write_text(f'''[Service]
WorkingDirectory={app}
Environment=PYTHONPATH=
Environment=LEO_WEB_DIST={app}/web/dist
Environment=LEO_GRAPH_POSITION_MODEL={MODEL}
ExecStart=
ExecStart=/usr/bin/env PYTHONDONTWRITEBYTECODE=1 LEO_WEB_DIST={app}/web/dist {app}/.venv/bin/python -m leo.api.production_v6_lookup
''')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','leo-algo07-graph-position.service'],check=True)
    subprocess.run(['systemctl','restart','leo-api.service'],check=True)
    return dict(revision=REVISION,model=MODEL,minimum_completed_utc_ns=cutoff,
                numerical_release=str(numerical),api_release=str(app),
                unit=str(unit),api_override=str(override),prior_api_override=str(old),
                activation_utc_ns=time.time_ns(),acquisition_changed=False)


if __name__=='__main__':
    print(json.dumps(activate(),indent=2))
