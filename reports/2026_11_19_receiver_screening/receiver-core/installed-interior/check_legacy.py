"""Rebuild the four existing profiles using the exact pre-change builder bytes."""

import argparse
import gzip
import os
from pathlib import Path

from tools.pipeline_eval import cavity_runtime as runtime
from tools.pipeline_eval.__main__ import local_output, save_json

OLD = "cd5f6923abbf673418e359e65d3865b9e397f4cc673d8fcddb30b871d7f7b516"
PROFILES = ("compact", "majority", "longitude", "phase-release")


def previous_builder():
    source = Path(runtime.__file__).read_bytes()
    begin = source.index(b"PROFILES =")
    stop = source.index(b"def release_files")
    names = b'PROFILES = ("compact", "majority", "longitude", "phase-release")\n\n\n'
    source = source[:begin] + names + source[stop:]
    source = source.replace(
        b'if profile in ("phase-release", "interior"):', b'if profile == "phase-release":'
    )
    source = source.replace(
        b'    if profile == "interior":\n        files[INTERIOR_RULE] = interior_rule()\n', b""
    )
    start = source.index(b'        launcher = Path(__file__).with_name("cavity_entry.py")')
    end = source.index(b"        command = ", start)
    entry = (
        b'        shutil.copyfile(Path(__file__).with_name("cavity_entry.py"),'
        b' out / "__main__.py")\n'
    )
    source = source[:start] + entry + source[end:]
    if runtime.digest(source) != OLD:
        raise ValueError("the reconstructed pre-change builder does not match its original hash")
    scope = dict(
        __name__=runtime.__name__, __file__=runtime.__file__, __package__=runtime.__package__
    )
    exec(compile(source, runtime.__file__, "exec"), scope)
    return source, scope["install"]


def ledger(root):
    return {
        str(path.relative_to(root)): runtime.digest(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def compare(work):
    old_source, old_install = previous_builder()
    builds = work / "compatibility"
    builds.mkdir(exist_ok=True)
    temp = work / "compiler-tmp"
    temp.mkdir(exist_ok=True)
    os.environ["TMPDIR"] = str(temp)
    matches = {}
    for profile in PROFILES:
        target = builds / profile
        old = ledger(old_install(target, profile=profile))
        target.rename(builds / (profile + "-before"))
        new = ledger(runtime.install(target, profile=profile))
        if old != new:
            raise ValueError(f"byte-level changes in the rebuilt {profile} profile")
        matches[profile] = dict(equal=True, files=new)
        print(profile, len(old), new["__main__.py"], flush=True)
    (work / "previous-builder.py.gz").write_bytes(gzip.compress(old_source, mtime=0))
    save_json(
        work / "compatibility.json",
        dict(
            previous_builder_sha256=OLD,
            current_builder_sha256=runtime.digest(Path(runtime.__file__).read_bytes()),
            identical_absolute_install_paths=True,
            comparisons=matches,
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    a = p.parse_args()
    compare(local_output(a.work))
