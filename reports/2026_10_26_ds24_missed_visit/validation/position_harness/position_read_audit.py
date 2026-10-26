"""Process-local inference read receipts; no production/runtime file changes."""
import atexit
import json
import os
from pathlib import Path
import sys


def forbidden(path,root):
    path=Path(path).resolve();root=Path(root).resolve()
    if path.suffix in ('.py','.pyc','.so'):return False
    lower=path.name.lower()
    if 'gps' in lower or 'oracle' in lower or lower.startswith('evaluation_site'):
        return True
    if path.is_relative_to(root):return False
    # The established scientific dependency environment is a /tmp symlink into
    # research storage; package metadata/data are libraries, not prior outcomes.
    if path.is_relative_to(Path('/tmp/algo03-feasible-deps').resolve()):return False
    if path.is_relative_to('/srv/bulk/leo/research'):return True
    repo=Path('/home/mouse9911/gits/leo-tracker-reduxredux')
    if path.is_relative_to(repo/'reports'):
        return path!=repo/'reports/2026_10_17_dsx01_full_data_tuning/graph/selected.json'
    return False


def install():
    root=os.environ.get('LEO_POSITION_RUN_ROOT');output=os.environ.get('LEO_POSITION_AUDIT_DIR')
    if not root or not output:return
    reads=set();denials=[];busy=False
    def hook(event,args):
        nonlocal busy
        if busy or event!='open':return
        path,mode,_=args
        if not isinstance(path,(str,bytes)) or mode is None or ('r' not in mode and '+' not in mode):return
        path=os.fsdecode(path);resolved=str(Path(path).resolve())
        reads.add(resolved)
        if forbidden(resolved,root):
            denials.append(resolved)
            raise RuntimeError('inference read outside frozen regional inputs: '+resolved)
    def save():
        nonlocal busy
        busy=True
        folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
        (folder/f'{os.getpid()}.json').write_text(json.dumps(dict(pid=os.getpid(),argv=sys.argv,
            run_root=root,read_paths=sorted(reads),denied_paths=denials),indent=2)+'\n')
    sys.addaudithook(hook);atexit.register(save)
