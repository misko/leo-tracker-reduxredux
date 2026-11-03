"""Bind completed evidence and verify previous immutable report outputs."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
PREVIOUS=['2026_10_16_dsx01_fast_association_losses','2026_10_16_dsx01_models',
          '2026_10_16_dsx01_iteration2','2026_10_16_dsx01_window_recovery',
          '2026_10_17_dsx01_recovery_snapshot']


def digest(path):return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    old=[]
    for name in PREVIOUS:
        root=REPORTS/name
        manifest=json.loads((root/'manifest.json').read_text())
        rows=manifest.get('files',manifest.get('outputs',[]))
        for row in rows:
            if digest(root/row['path']).removeprefix('sha256:')!=row['sha256'].removeprefix('sha256:'):
                raise ValueError(f'Previous immutable evidence changed: {root/row["path"]}')
        old.append(dict(path=str(root/'manifest.json'),sha256=digest(root/'manifest.json'),
                        verified_files=len(rows)))
    files=[]
    for path in sorted(HERE.rglob('*')):
        if not path.is_file() or path==HERE/'manifest.json':continue
        if any(p in {'.pytest_cache','__pycache__'} for p in path.relative_to(HERE).parts):continue
        files.append(dict(path=str(path.relative_to(HERE)),bytes=path.stat().st_size,sha256=digest(path)))
    (HERE/'manifest.json').write_text(json.dumps(dict(kind='DSX01-iteration3-evidence-snapshot',
        created_utc=datetime.now(timezone.utc).isoformat(),goal_status='active',
        previous_immutable_inputs=old,files=files),indent=2)+'\n')
    print(json.dumps(dict(files=len(files),bytes=sum(f['bytes'] for f in files),
        previous_verified_files=sum(f['verified_files'] for f in old))))


if __name__=='__main__':main()
