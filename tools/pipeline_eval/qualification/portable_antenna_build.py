"""Build a standalone conditional antenna receiver from the verified saved-IQ release."""

import argparse
import gzip
import io
import shutil
import tarfile

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from . import portable_antenna_stream as stream
from .full_v5_check import _sha
from .portable_conditional_build import REPORT as PREVIOUS
from .portable_mode_build import replace

BASE = "61aba4361822ed2a4f0bbbddd551436d92fd83358f5c7efadeabb1d385031330"
REPORT = PREVIOUS.parents[1] / "antenna-confirmation/portable-stream"
ARCHIVE = "portable-antenna-receiver.tar.gz"
HIT = "partner-on-strict-primary-hit/observed-packets-v1"


def bridge(source):
    # Preserve the existing stock reader, quality contract, packet writer and segment accounting.
    source = replace(source, "*, outputs=None):", "*, outputs=None, observation_factory=None):")
    source = replace(
        source,
        "    with NativeShortWindow(",
        "    factory = observation_factory or NativeShortWindow\n    with factory(",
    )
    source = replace(
        source,
        "            for window in source.windows():",
        "            records = (native(source, policy) if observation_factory else\n"
        "                       ((window, None) for window in source.windows()))\n"
        "            for window, measured in records:",
    )
    original = "status = analyze_window(window, source.receiver_ids, None, policy, detector=detect)"
    return replace(
        source,
        "                " + original,
        "                if measured is None:\n"
        f"                    {original}\n"
        "                else:\n"
        "                    status, probes, cpu_s = measured\n"
        "                    detector_cpu_s += cpu_s",
    )


def policy(source):
    source = replace(
        source, "def mark(document, probes):", "def mark(document, probes, policy=POLICY):"
    )
    source = replace(source, "        POLICY,", "        policy,")
    source = replace(
        source, "scope=POLICY, detector_mode=POLICY", "scope=policy, detector_mode=policy"
    )
    source = replace(
        source,
        "def detect(native, samples, receiver_id, *, include_timings=False):",
        "def detect(native, samples, receiver_id, *, on_hit=False, include_timings=False):",
    )
    return replace(
        source,
        'needed = needs_partner({"candidates": factors})',
        'needed = positive({"candidates": factors}) == on_hit',
    )


def entry(source):
    source = replace(
        source, 'deadline, detector="stock"):', 'deadline, detector="stock", visit_workers=1):'
    )
    source = replace(
        source,
        "    job = bindings(source)",
        '    if visit_workers not in (1, 2) or (detector == "stock" and visit_workers != 1):\n'
        '        raise ValueError("visit workers apply to conditional antenna modes")\n'
        "    job = bindings(source)",
    )
    source = replace(
        source,
        "        detector=detector,",
        "        detector=detector,\n        visit_workers=visit_workers,",
    )
    source = replace(
        source, 'if job["detector"] == "second-on-miss":', 'if job["detector"] != "stock":'
    )
    paths = 'if detector == "second-on-miss":'
    if source.count(paths) != 2:
        raise ValueError("the conditional package acquisition and handoff ports changed")
    source = source.replace(paths, 'if detector != "stock":')
    source = replace(
        source, "from conditional_policy import mark", "from conditional_policy import POLICY, mark"
    )
    source = replace(
        source,
        'doc = mark(doc, doc["source"]["probes"])',
        f'mode = {HIT!r} if detector == "partner-on-hit" else POLICY\n'
        '        doc = mark(doc, doc["source"]["probes"], mode)',
    )
    source = replace(
        source,
        'choices=("stock", "second-on-miss"), default="stock")',
        'choices=("stock", "second-on-miss", "partner-on-hit"), default="stock")\n'
        '    parser.add_argument("--visit-workers", type=int, choices=(1, 2), default=1)',
    )
    return replace(
        source,
        "args.raw_deadline, args.detector)",
        "args.raw_deadline, args.detector, args.visit_workers)",
    )


def build(parent, report=REPORT):
    parent.mkdir(parents=True, exist_ok=False)
    archive = whole_iq.checked(PREVIOUS / "portable-receiver-conditional.tar.gz", BASE)
    with tarfile.open(archive) as bundle:
        bundle.extractall(parent, filter="data")
    folder = parent / "portable-receiver"
    manifest = folder / "files.json"
    previous = whole_iq.read(manifest)
    files = previous["files"]
    for name, digest in files.items():
        whole_iq.checked(folder / name, digest)
    for name, transform in (
        ("receive.py", entry),
        ("capture/native_bridge.py", bridge),
        ("capture/conditional_policy.py", policy),
    ):
        target = folder / name
        target.write_text(transform(target.read_text()))
    shutil.copyfile(stream.__file__, folder / "capture/conditional_capture.py")
    shutil.copyfile(report / "USAGE.md", folder / "README.md")
    updated = {name: _sha(folder / name) for name in files}
    save_json(manifest, dict(previous, files=updated))
    manifest.chmod(0o644)
    report.mkdir(parents=True, exist_ok=True)
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as bundle:
        for name in sorted([*updated, "files.json"]):
            body = (folder / name).read_bytes()
            item = tarfile.TarInfo("portable-receiver/" + name)
            item.size, item.mode = len(body), 0o644
            bundle.addfile(item, io.BytesIO(body))
    dest = report / ARCHIVE
    write(dest, gzip.compress(data.getvalue(), compresslevel=6, mtime=0))
    write(report / "SHA256SUMS", f"{_sha(dest)}  {ARCHIVE}\n".encode())
    changed = [name for name in updated if updated[name] != files[name]]
    save_json(
        report / "release.json",
        dict(
            previous_archive_sha256=BASE,
            archive_sha256=_sha(dest),
            manifest_sha256=_sha(manifest),
            manifest_entries=len(updated),
            application_files=len(
                updated.keys() - {"README.md", "requirements.txt", "example-input.json"}
            ),
            compressed_bytes=dest.stat().st_size,
            changed=sorted(changed),
            native_files={name: digest for name, digest in updated.items() if name.endswith(".so")},
            observed_hit_identity=HIT,
        ),
    )
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_build_directory", type=local_output)
    parser.add_argument("--report", type=local_output, default=REPORT)
    args = parser.parse_args()
    print(build(args.new_build_directory, args.report))
