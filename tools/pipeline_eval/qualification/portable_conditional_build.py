"""Extend the authenticated stock portable package with the frozen partner-on-miss rule."""

import argparse
import shutil
import tarfile
from textwrap import indent

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..variants import negative_rescue, second_on_miss, single_chain, staggered_native
from . import one_lane_whole_raw, portable_conditional_capture, second_on_miss_whole_raw
from .full_v5_check import _sha
from .portable_mode_build import BASE, replace
from .portable_mode_build import REPORT as STAGGERED
from .portable_receiver_build import STOCK, definitions

REPORT = STAGGERED.parents[1] / "pilot-influence/portable-conditional"
BASE_TAR = BASE / "portable-receiver.tar.gz"
BASE_SHA = "0f9d541a5242b3c9f66bcc81d568c3497fa80c7909528e4d71a32081c2af1a35"
BASE_MANIFEST = "058367e314034d26e24a79544d25c9e01eeed5b9f2d7b933d201aa11d0551528"


def bridge(source):
    """Give the stock reader a chronological output port with the same two lane files."""
    source = replace(
        source,
        'def stream_range(library, worker, segments, case_id, capture=None, detector="ordinary"):',
        'def stream_range(library, worker, segments, case_id, capture=None, detector="ordinary", '
        "*, outputs=None):",
    )
    source = replace(
        source,
        "        for index in range(worker, len(segments), 2):",
        "        indices = range(len(segments)) if outputs is not None else "
        "range(worker, len(segments), 2)\n"
        "        for index in indices:\n"
        "            sink = sys.stdout if outputs is None else outputs[index % 2]",
    )
    source = replace(
        source,
        "                    flush=True,\n                )\n                count += 1",
        "                    file=sink,\n                    flush=True,\n                )\n"
        "                count += 1",
    )
    source = replace(
        source,
        "                flush=True,\n            )\n            print(\n"
        '                f"Segment {index}',
        "                file=sink,\n                flush=True,\n"
        "            )\n            print(\n"
        '                f"Segment {index}',
    )
    return replace(
        source,
        '    print(encoded(dict(kind="worker", worker=worker)), flush=True)',
        "    terminals = ((worker, sys.stdout),) if outputs is None else enumerate(outputs)\n"
        "    for lane, sink in terminals:\n"
        '        print(encoded(dict(kind="worker", worker=lane)), file=sink, flush=True)',
    )


def entry(source):
    source = replace(
        source,
        '        bridge.stream_range(\n            ROOT / "stock-wide.so", lane, '
        'job["segments"], "saved-recording", job["authority"]\n        )',
        '        if job["detector"] == "second-on-miss":\n'
        "            from conditional_capture import capture\n\n"
        "            capture(job)\n"
        "        else:\n"
        '            bridge.stream_range(\n                ROOT / "stock-wide.so", lane, '
        'job["segments"], "saved-recording", job["authority"]\n            )',
    )
    source = replace(
        source,
        "def replay(source, out, cpus, deadline):",
        'def replay(source, out, cpus, deadline, detector="stock"):',
    )
    source = replace(
        source,
        '        detector_sha256=lock["files"]["stock-wide.so"],',
        '        detector=detector,\n        detector_sha256=lock["files"]["stock-wide.so"],',
    )
    start = source.index(
        "    try:\n        with ExitStack() as stack:", source.index("def replay(")
    )
    end = source.index("    raw_end = memory()", start)
    source = (
        source[:start]
        + '    if detector == "second-on-miss":\n'
        + '        subprocess.run([sys.executable, "-IB", __file__, "_raw", str(plan), "0"],\n'
        + "                       timeout=deadline, check=True)\n"
        + "    else:\n"
        + indent(source[start:end], "    ")
        + source[end:]
    )
    source = replace(
        source,
        '    native = out / "native.json"',
        '    if detector == "second-on-miss":\n'
        "        from conditional_policy import mark\n\n"
        "        del lanes\n"
        '        doc = mark(doc, doc["source"]["probes"])\n'
        '    native = out / "native.json"',
    )
    source = replace(
        source,
        '    parser.add_argument("--raw-deadline",',
        '    parser.add_argument("--detector", choices=("stock", "second-on-miss"), '
        'default="stock")\n'
        '    parser.add_argument("--raw-deadline",',
    )
    return replace(
        source, "args.cpus, args.raw_deadline)", "args.cpus, args.raw_deadline, args.detector)"
    )


EXTRACTS = (
    (negative_rescue, ("positive",)),
    (second_on_miss, ("needs_partner", "mark")),
    (staggered_native, ("RfStagger",)),
    (single_chain, ("analyze_native",)),
    (one_lane_whole_raw, ("stereo_slots",)),
    (second_on_miss_whole_raw, ("detect",)),
)


def policy():
    parts = [
        "import json\nfrom hashlib import sha256\nimport numpy as np\n"
        "from native_bridge import _from_native\n",
        f"POLICY = {second_on_miss.POLICY!r}\nGATE = {negative_rescue.GATE!r}\n",
    ]
    for module, names in EXTRACTS:
        code = definitions(module, names)
        if module is second_on_miss_whole_raw:
            code = replace(code, "second_on_miss.needs_partner(", "needs_partner(")
            code = replace(
                code, "STEREO(primary, receiver_id)", "stereo_slots(primary, receiver_id)"
            )
        parts.append(code)
    return "\n\n".join(parts) + "\n"


def build(parent):
    parent.mkdir(parents=True, exist_ok=False)
    with tarfile.open(whole_iq.checked(BASE_TAR, BASE_SHA)) as archive:
        archive.extractall(parent, filter="data")
    out = parent / "portable-receiver"
    lock = whole_iq.read(whole_iq.checked(out / "files.json", BASE_MANIFEST))
    if lock["files"]["stock-wide.so"] != STOCK:
        raise ValueError("stock-only base does not bind the released ABI")
    for name, sha in lock["files"].items():
        whole_iq.checked(out / name, sha)
    for name, convert in (("receive.py", entry), ("capture/native_bridge.py", bridge)):
        path = out / name
        path.write_text(convert(path.read_text()))
    (out / "capture/conditional_policy.py").write_text(policy())
    shutil.copyfile(portable_conditional_capture.__file__, out / "capture/conditional_capture.py")
    pins = {
        str(p.relative_to(out)): _sha(p)
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "files.json"
    }
    save_json(out / "files.json", dict(lock, files=pins))
    (out / "files.json").chmod(0o644)
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=local_output)
    print(build(parser.parse_args().parent))
