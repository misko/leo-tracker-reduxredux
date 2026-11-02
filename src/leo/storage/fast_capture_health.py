"""Read-only checkpoint facts for abandoned fast-capture reconciliation."""
from leo.storage.continuous_window import read_checkpoint


def checkpoint_health(root):
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not (path/'run.json').is_file():continue
        try:
            cp=read_checkpoint(root,path.name)
            yield dict(run_id=cp.run_id,state=cp.state,updated_utc_ns=cp.updated_utc_ns)
        except (OSError,ValueError) as error:
            yield dict(run_id=path.name,state='invalid',updated_utc_ns=(path/'run.json').stat().st_mtime_ns,
                       error=f'{type(error).__name__}: {error}'[:512])
