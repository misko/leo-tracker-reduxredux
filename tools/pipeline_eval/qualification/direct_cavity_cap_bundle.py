"""Stage the direct cavity source with a scan-scoped zero-retention TLE parser."""

import argparse
import shutil
import subprocess
from pathlib import Path

from . import direct_cavity_cap as cap
from . import direct_cavity_trial as direct

REPLACEMENTS = (
    (
        "    from leo.application.localization_v3 import prepare_native_scan\n",
        "    from leo.analysis.localization_v3.elements import ElementParser\n"
        "    from leo.application.localization_v3 import prepare_native_scan\n",
    ),
    (
        "            screen_longitude_deg=screen_center[1],\n",
        "            screen_longitude_deg=screen_center[1],\n"
        "            element_parser=ElementParser(maximum_bytes=0),\n",
    ),
)


def bounded_source(source):
    for old, new in REPLACEMENTS:
        if source.count(old) != 1:
            raise ValueError("unrecognized direct cavity preparation source")
        source = source.replace(old, new, 1)
    compile(source, direct.ENTRY, "exec")
    return source


def stage(work, original):
    root = direct.local_output(work)
    plan = direct.common.read(root / "plan.json")
    base = original.resolve() / "bundle.json"
    if plan["source"] != cap.source(direct) or direct.common.sha(base) != plan["bundle_sha256"]:
        raise ValueError("baseline release or cap protocol changed")
    before = {}
    for key in cap.ROSTER:
        p = root / "runs" / key / cap.DIRECT / "measurement.json"
        row = direct.common.read(p)
        if (
            row["service_result"] != "oom-kill"
            or row["stages"][-1]["name"] != "prepare_native_scan"
        ):
            raise ValueError(
                "the zero-retention trial requires the observed preparation cap failure"
            )
        before[key] = direct.common.sha(p)
    output = root / "bounded"
    output.mkdir(exist_ok=False)
    donor = original / direct.RELEASE
    ledger = direct.common.read(base)
    hashes = {}
    for name, expected in ledger["files"].items():
        src, dst = donor / name, output / name
        if direct.common.sha(src) != expected:
            raise ValueError(f"immutable staged donor changed: {name}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        if name == direct.ENTRY:
            dst.write_text(bounded_source(src.read_text()))
        else:
            shutil.copyfile(src, dst)
        hashes[name] = direct.common.sha(dst)
    if {k for k in hashes if hashes[k] != ledger["files"][k]} != {direct.ENTRY}:
        raise ValueError("bounded release changed more than the declared call site")
    script = (
        "from leo.analysis.localization_v4.backend import build_native; "
        "import sys; build_native(sys.argv[1])"
    )
    subprocess.run(
        [str(direct.v5_lean.PYTHON), "-B", "-c", script, str(output / "native")],
        cwd=output,
        env=direct.command_env(output),
        check=True,
        timeout=40,
    )
    if direct.common.sha(output / "native/native_bound.so") != ledger["binary"]:
        raise ValueError("the native bound should remain byte-identical")
    manifest = root / "bounded-bundle.json"
    direct.save_json(manifest, dict(ledger, files=hashes))
    direct.save_json(
        root / "bounded-lock.json",
        dict(
            baseline_bundle_sha256=plan["bundle_sha256"],
            bundle_sha256=direct.common.sha(manifest),
            source_before=ledger["files"][direct.ENTRY],
            source_after=hashes[direct.ENTRY],
            baseline_measurements=before,
            build_recipe_sha256=direct.common.sha(Path(__file__)),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("original", type=Path)
    a = p.parse_args()
    stage(a.work, a.original)
