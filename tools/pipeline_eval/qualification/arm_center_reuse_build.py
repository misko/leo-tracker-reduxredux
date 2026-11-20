"""Rebuild isolated scalar and portable paired fractional search variants."""

import argparse
import json
import os
import shutil
from pathlib import Path

from ..__main__ import ROOT, local_output, save_json
from ..variants import arm_center_pair, glrt_center_cell
from . import arm_receiver_build as parent
from .full_v5_check import _sha

REPORT = parent.REPORT.parents[1] / "receiver-choice/arm-center-reuse"
WORK = parent.WORK.with_name("arm-center-reuse-v2")
MODES = ("original", "center", "pair")
ARCH = ("host", "arm64")
PARENT_BUILD = {
    "host": "8d04faaf983d181768a9b363de660042accecb8bd086d47e62ed49810181e4fa",
    "arm64": "76010cacc43b92c8e0b3ac7acc990c5d0c3d83c4c34779b88c52f75176932cb7",
}
SEARCH = "kernel/private/full_search.c"
PRESENCE = "kernel/private/native_presence/presence.c"


def read(path):
    return json.loads(path.read_bytes())


def trace_stream(source):
    line = '            fputs(",\\"top16\\":[", stdout);'
    emitted = r"""            uint64_t work[4];
            leo_arm_center_trace(work);
            printf(",\"work\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]",
                work[0],work[1],work[2],work[3]);
"""
    if source.count(line) != 1:
        raise ValueError("sealed chronological runner changed")
    header = '#include "center_union.h"\n'
    return source.replace(
        header, header + "void leo_arm_center_trace(uint64_t result[4]);\n"
    ).replace(line, emitted + line)


def stage(work, mode, trace):
    folder = work / (mode + ("-trace" if trace else ""))
    clone = folder / "source"
    shutil.copytree(parent.SOURCE, clone, ignore=shutil.ignore_patterns("__pycache__"))
    search = clone / SEARCH
    search.write_text(arm_center_pair.search(search.read_text(), mode, trace))
    if mode == "pair":
        source = clone / PRESENCE
        source.write_text(arm_center_pair.paired_presence(source.read_text()))
        shutil.copyfile(arm_center_pair.HEADER, source.with_name(arm_center_pair.HEADER.name))
    if trace:
        (folder / "arm_receiver_stream.c").write_text(trace_stream(parent.LAUNCHER.read_text()))
    return folder, clone


def build(work, arch):
    if len(os.sched_getaffinity(0)) != 1 or not os.sched_getaffinity(0) <= {8, 9}:
        raise ValueError("use a pinned build CPU 8 or 9")
    (work / "compiler-temp").mkdir(parents=True, exist_ok=True)
    receipt_path = parent.check(parent.REPORT / f"build-{arch}.json", PARENT_BUILD[arch])
    prior = read(receipt_path)
    for name, digest in prior["sources"].items():
        parent.check(ROOT / name, digest)
    for name, digest in prior["detector_source_manifest"].items():
        parent.check(parent.SOURCE / name, digest)
    for name, digest in prior["fftw_libraries"].items():
        parent.check(Path(name), digest)
    parent.check(Path(prior["compiler"]["path"]), prior["compiler"]["sha256"])
    common, link = prior["commands"][:-1], prior["commands"][-1]
    dependencies = {cmd[-1]: _sha(Path(cmd[-1])) for cmd in common}
    original = dict(prior["executable"])
    parent.check(Path(original["path"]), original["sha256"])
    artifacts = {"original": original}
    for mode in MODES:
        for trace in (False, True):
            if mode == "original" and not trace:
                continue
            name = mode + ("-trace" if trace else "")
            folder, source = stage(work / arch, mode, trace)
            command_record, changed = [], {}
            for cmd in common:
                filename, obj = Path(cmd[cmd.index("-c") + 1]), cmd[-1]
                if filename == parent.SOURCE / "native_glrt.c":
                    rebuilt = [x.replace(str(parent.SOURCE), str(source)) for x in cmd]
                elif trace and filename == parent.LAUNCHER:
                    rebuilt = [
                        str(folder / filename.name) if x == str(filename) else x for x in cmd
                    ]
                else:
                    continue
                new = str(folder / Path(obj).name)
                rebuilt[-1] = new
                if trace:
                    rebuilt.insert(1, "-DLEO_ARM_CENTER_TRACE")
                parent.command(work, rebuilt, timeout=40)
                changed[obj] = new
                command_record.append(rebuilt)
            target = folder / "receiver"
            linked = [changed.get(x, x) for x in link]
            linked[-1] = str(target)
            parent.command(work, linked, timeout=65)
            command_record.append(linked)
            differences = {
                key: _sha(source / key)
                for key in prior["detector_source_manifest"]
                if _sha(source / key) != prior["detector_source_manifest"][key]
            }
            if set(differences) != ({SEARCH, PRESENCE} if mode == "pair" else {SEARCH}):
                raise ValueError("paired overlay changed extra detector source")
            artifacts[name] = dict(
                path=str(target),
                sha256=_sha(target),
                bytes=target.stat().st_size,
                commands=command_record,
                source_changes=differences,
                extra_header_sha256=_sha(arm_center_pair.HEADER) if mode == "pair" else None,
            )
    sources = [
        Path(__file__),
        Path(arm_center_pair.__file__),
        arm_center_pair.HEADER,
        Path(glrt_center_cell.__file__),
        Path(arm_center_pair.presence.__code__.co_filename),
        REPORT / "PROTOCOL.md",
    ]
    save_json(
        work / f"build-{arch}.json",
        dict(
            old_build_sha256=PARENT_BUILD[arch],
            old_object_hashes=dependencies,
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
            artifacts=artifacts,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arch", choices=ARCH)
    parser.add_argument("--work", type=local_output, default=WORK)
    args = parser.parse_args()
    build(args.work, args.arch)
