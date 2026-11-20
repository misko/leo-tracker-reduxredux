"""Extend the sealed saved-IQ bundle with the exact native staggered mode."""

import argparse
import shutil
import tarfile
from pathlib import Path, PurePosixPath
from textwrap import indent

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json
from . import arrival_queue, portable_staggered_capture, staggered_whole
from .full_v5_check import _sha
from .portable_receiver_build import definitions

REPORT = staggered_whole.REPORT.with_name("portable-mode")
BASE = REPORT.parents[1] / "latency-and-support/portable-receiver"
NATIVE = "libleo-staggered-native.so"
CORE = "libleo-adaptive-detector.so.1"
BUILD_SHA = "7011f777eadf8027e64b2582d57ba3034622ca42ecbbd33a736770326d5bd597"
WRAPPERS = (
    "staggered_native",
    "dual_lane",
    "center_union",
    "differential_pilot",
    "differential_runtime",
    "frame_coherence",
    "hinted_glrt",
    "wide_regional",
)


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError("the sealed public receiver no longer has the expected adapter port")
    return source.replace(old, new)


def entry(source):
    source = replace(
        source,
        "def replay(source, out, cpus, deadline):",
        'def replay(source, out, cpus, deadline, detector="stock"):',
    )
    source = replace(
        source,
        'detector_sha256=lock["files"]["stock-wide.so"],',
        'detector=detector,\n        detector_sha256=lock["files"]['
        '"stock-wide.so" if detector == "stock" else\n'
        '            "capture/mode_assets/libleo-staggered-native.so"\n        ],',
    )
    begin = source.index(
        "    try:\n        with ExitStack() as stack:", source.index("def replay(")
    )
    end = source.index("    raw_end = memory()", begin)
    start_mode = (
        '    if detector == "staggered":\n'
        '        subprocess.run([sys.executable, "-IB", __file__, "_staggered", str(plan)],\n'
        "                       timeout=deadline, check=True)\n"
        "    else:\n"
    )
    source = source[:begin] + start_mode + indent(source[begin:end], "    ") + source[end:]
    source = replace(
        source,
        "    if len(sys.argv) >= 3 and sys.argv[1] in",
        '    if len(sys.argv) == 3 and sys.argv[1] == "_staggered":\n'
        "        raw_bridge()\n"
        "        from portable_staggered import capture\n"
        "        capture(read(sys.argv[2]))\n"
        '        verify_loaded(ROOT / "capture")\n'
        "        return\n"
        "    if len(sys.argv) >= 3 and sys.argv[1] in",
    )
    source = replace(
        source,
        '    parser.add_argument("--raw-deadline",',
        (
            '    parser.add_argument("--detector", choices=("stock", "staggered"), '
            'default="stock")\n'
            '    parser.add_argument("--raw-deadline",'
        ),
    )
    return replace(
        source, "args.cpus, args.raw_deadline)", "args.cpus, args.raw_deadline, args.detector)"
    )


def unpack(old, out):
    expected = whole_iq.read(BASE / "package-lock.json")["files"][old.name]
    whole_iq.checked(old, expected)
    with tarfile.open(old, "r:gz") as release:
        for item in release.getmembers():
            rel = PurePosixPath(item.name)
            if not item.isfile() or rel.parts[0] != "portable-receiver" or ".." in rel.parts:
                raise ValueError("the original application bundle contained an invalid member")
            leaf = out.joinpath(*rel.parts[1:])
            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_bytes(release.extractfile(item).read())
    lock = whole_iq.read(out / "files.json")
    for name, pin in lock["files"].items():
        whole_iq.checked(out / name, pin)
    return lock


def packet_source():
    return (
        "from types import SimpleNamespace\n"
        "from hashlib import sha256\n"
        "from time import monotonic_ns, thread_time_ns\n"
        "import native_bridge as recording_to_v5\n"
        "def fingerprint(value):\n"
        "    return sha256(recording_to_v5.encoded(value).encode()).hexdigest()\n\n"
        + definitions(arrival_queue, ("native_visit",))
        + "\n\narrival_queue = SimpleNamespace(native_visit=native_visit, "
        "fingerprint=fingerprint)\n\n" + definitions(staggered_whole, ("run_visit",)) + "\n"
    )


def build(out, native):
    old = BASE / "portable-receiver.tar.gz"
    measured = whole_iq.read(whole_iq.checked(native / "build.json", BUILD_SHA))
    out.mkdir(parents=True, exist_ok=False)
    base = unpack(old, out)
    mode = out / "capture/mode_assets"
    mode.mkdir()
    (mode / "__init__.py").write_text('"""Qualified staggered mode dependencies."""\n')
    variants = ROOT / "tools/pipeline_eval/variants"
    for name in WRAPPERS:
        leaf = variants / (name + ".py")
        expected = measured["sources"].get(str(leaf))
        if expected:
            whole_iq.checked(leaf, expected)
        shutil.copyfile(leaf, mode / leaf.name)
    for name in (CORE, NATIVE):
        shutil.copyfile(whole_iq.checked(native / name, measured["files"][name]), mode / name)
    shutil.copyfile(portable_staggered_capture.__file__, out / "capture/portable_staggered.py")
    (out / "capture/staggered_packets.py").write_text(packet_source())
    command = out / "receive.py"
    command.write_text(entry(command.read_text()))
    added = [
        p
        for p in (out / "capture").rglob("*")
        if p.is_file() and str(p.relative_to(out)) not in base["files"]
    ]
    files = base["files"] | {str(p.relative_to(out)): _sha(p) for p in (*added, command)}
    save_json(
        out / "files.json",
        dict(
            base,
            files=files,
            staggered_build_sha256=BUILD_SHA,
            original_archive_sha256=_sha(old),
            packaged_modes=["stock", "staggered"],
            change_scope=["entry dispatch", "chronological RF mode", "dual-lane native libraries"],
        ),
    )
    for p in (out / "files.json", out / "position/native/manifest.json"):
        p.chmod(0o644)
    return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=local_output)
    parser.add_argument("native", type=Path)
    args = parser.parse_args()
    print(len(build(args.out, args.native)), "pinned application assets")
