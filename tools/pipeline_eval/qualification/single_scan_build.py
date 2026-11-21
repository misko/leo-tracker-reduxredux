"""Build the one-scan receiver and cancellation comparator from the same verified sources."""

import subprocess
from pathlib import Path

from .full_v5_check import REPO, _sha
from .reverse_glrt_reference import packed
from .reverse_glrt_report import read
from .single_scan_roster import OUT, PRIOR, WORK, initial_driver

SOURCE = REPO / "tools/pipeline_eval/variants/single_scan_receiver.c"


def build(out, work):
    old = read(PRIOR / "embedded-builds.json")
    for name, sha in old["sources"].items():
        if _sha(REPO / name) != sha:
            raise ValueError("frozen receiver source changed")
    folder = work / "bin"
    folder.mkdir(parents=True, exist_ok=True)
    builds = {}
    for arch, recipe in old["builds"].items():
        for method in ("single_scan", "cancellation"):
            shared = arch == "x86-64"
            if method == "cancellation" and not shared:
                continue
            command = list(recipe["command"][:-2])
            if method == "single_scan":
                command = [
                    v
                    for v in command
                    if Path(v).name not in ("timing_first_receiver.c", "pilot_cancel.c")
                ]
                old_driver = str(SOURCE.with_name("two_carrier_receiver.c"))
                command[command.index(old_driver)] = str(SOURCE)
            if shared:
                command = [
                    v for v in command if v != "-static" and Path(v).name != "two_carrier_iq.c"
                ]
                command[1:1] = ["-shared", "-fPIC"]
            target = folder / (f"{method}-{arch}" + (".so" if shared else ""))
            command += ["-o", str(target)]
            subprocess.run(command, check=True)
            builds[f"{method}-{arch}"] = dict(
                path=str(target), sha256=_sha(target), command=command
            )
        if arch == "x86-64":
            cmd = list(old["builds"][arch]["command"][:-2])
            cmd = [
                v for v in cmd if Path(v).name not in ("timing_first_receiver.c", "pilot_cancel.c")
            ]
            cmd[cmd.index(str(SOURCE.with_name("two_carrier_receiver.c")))] = str(SOURCE)
            target = folder / "single_scan-host"
            cmd += ["-o", str(target)]
            subprocess.run(cmd, check=True)
            builds["single_scan-host"] = dict(path=str(target), sha256=_sha(target), command=cmd)
    path = out / "builds.json"
    sources = dict(old["sources"], **{str(SOURCE.relative_to(REPO)): _sha(SOURCE)})
    receipt = dict(
        builds=builds,
        sources=sources,
        previous=_sha(PRIOR / "embedded-builds.json"),
        assets=old["assets"],
        driver=initial_driver(out, Path(__file__)),
        protocol=_sha(out / "PROTOCOL.md"),
    )
    if path.exists() and read(path) != receipt:
        raise ValueError("frozen candidate build changed")
    path.write_bytes(packed(receipt) + b"\n")
    return receipt


if __name__ == "__main__":
    build(OUT, WORK)
