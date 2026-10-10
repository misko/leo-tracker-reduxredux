"""One-shot, stopped-writer relocation of research output; never touches QNAP."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat

HERE = Path(__file__).resolve().parent
TARGET = Path('/srv/bulk/leo/research/position-error-iter164-results')


def inventory(root):
    result = {}
    for folder, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories+files):
            path = Path(folder)/name
            relative = str(path.relative_to(root))
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError('unexpected nonregular entry: '+relative)
            if name.startswith('.'):
                raise ValueError('unexpected hidden/unfinished entry: '+relative)
            record = dict(kind='directory' if path.is_dir() else 'file', mode=stat.S_IMODE(info.st_mode))
            if path.is_file():
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''):digest.update(block)
                record.update(bytes=info.st_size, sha256=digest.hexdigest())
            result[relative] = record
    return dict(sorted(result.items()))


def no_writers():
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try: command = path.read_bytes()
        except (FileNotFoundError, ProcessLookupError):continue
        if b'position_error_iter164/' in command and any(
                name in command for name in (b'/batch.py', b'/execute.py')):
            raise ValueError('research writer still present: '+path.parent.name)


def main():
    # Imported only for metadata/closure verification; no scientific calls.
    from batch import prior_batches
    from execute import verify
    from leo.contracts.digests import canonical_digest
    plan = json.loads((HERE/'protocol.json').read_text())
    verify(plan)
    source = HERE/'results'
    backup = HERE/'results.batch0-backup'
    staging = TARGET.with_name(TARGET.name+'.staging')
    receipt = HERE/'STORAGE_RELOCATION.json'
    manifest = HERE/'STORAGE_MANIFEST.json'
    for path in (source, backup, staging, TARGET):
        if path.resolve().is_relative_to('/mnt/qnap01'):
            raise ValueError('QNAP paths forbidden')
    if source.is_symlink() or not source.is_dir():raise ValueError('original results directory required')
    if any(p.exists() or p.is_symlink() for p in (backup, staging, TARGET, receipt, manifest)):
        raise ValueError('relocation already started; inspect rather than retry')
    no_writers()
    prior_batches(source, 1, canonical_digest(plan), plan['execution_batches'])
    if list(source.glob('batch-1-*')):raise ValueError('later resource batch already claimed')
    before = inventory(source)
    size = sum(r.get('bytes', 0) for r in before.values())
    if shutil.disk_usage(TARGET.parent).free < size+1024**3:
        raise ValueError('insufficient bulk space')
    shutil.copytree(source, staging, copy_function=shutil.copy2)
    if inventory(staging) != before or inventory(source) != before:
        raise ValueError('source/copy mismatch; retain both, do not cut over')
    no_writers()
    with manifest.open('x') as stream:
        json.dump(before, stream, indent=2);stream.write('\n')
    staging.rename(TARGET)
    source.rename(backup)
    source.symlink_to(TARGET, target_is_directory=True)
    if inventory(source) != before or inventory(backup) != before:
        raise ValueError('post-cutover mismatch; keep backup, do not resume')
    # Probe exclusive same-directory hard links outside scientific artifacts.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='iter164-link-probe-', dir=TARGET.parent) as folder:
        a, b = Path(folder)/'a', Path(folder)/'b'
        with a.open('x') as stream:stream.write('probe')
        os.link(a, b)
        try:os.link(a, b)
        except FileExistsError:pass
        else:raise ValueError('exclusive link semantics unavailable')
        if b.read_text() != 'probe':raise ValueError('link content mismatch')
    verify(plan)
    row = dict(status='verified', protocol_sha256=canonical_digest(plan),
               original_path=str(source), bulk_path=str(TARGET), backup_path=str(backup),
               entries=len(before), regular_files=sum(r['kind']=='file' for r in before.values()),
               bytes=size, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
               source_copy_recheck=True, symlink_recheck=True, backup_retained=True,
               hardlink_probe=True, frozen_numerical_closure_unchanged=True)
    with receipt.open('x') as stream:json.dump(row, stream, indent=2);stream.write('\n')
    print(json.dumps(row), flush=True)


if __name__ == '__main__':main()
