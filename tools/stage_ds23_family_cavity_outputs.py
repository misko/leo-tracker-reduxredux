"""Move only terminal generated case files to bulk, preserving verified bytes.

Live workers keep the same paths via symlinks. A progress receipt is written
only after a case writer closes its result; files without that receipt stay put.
No input corpus, QNAP path or unrelated workspace artifact is modified.
"""

import hashlib
from pathlib import Path
import re
import shutil

from run_algo01_ds23_sample import ROOT,read

SOURCE=ROOT/'reports/2026_10_22_ds23_family_cavity/phase_refreshed/full_DS23'
TARGET=Path('/srv/bulk/leo/research/ds23-family-cavity-full-20261022')


def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):result.update(block)
    return result.hexdigest()


def relocate(source,target):
    if source.is_symlink():return 0
    target.parent.mkdir(parents=True,exist_ok=True);size=source.stat().st_size
    if not target.exists():shutil.copy2(source,target)
    if digest(source)!=digest(target):raise ValueError('bulk copy differs; original retained')
    source.unlink();source.symlink_to(target);return size


def main():
    total=0;files=0
    for stage in ['nominations','positions']:
        progress=SOURCE/(stage+'_progress.json')
        if not progress.exists():continue
        for row in read(progress)['receipts']:
            case=row['case']
            if not re.fullmatch(r'DS23-\d{4}',case):raise ValueError('unexpected case identifier')
            relative=Path(case+'_nominations.json') if stage=='nominations' else Path('position')/(case+'.json')
            source=SOURCE/relative
            if source.exists() and not source.is_symlink():total+=relocate(source,TARGET/relative);files+=1
    print(dict(files_relocated=files,bytes_reclaimed=total,target=str(TARGET)),flush=True)


if __name__=='__main__':main()
