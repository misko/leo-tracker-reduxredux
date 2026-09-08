"""Archive selected non-payload evidence; never credentials, IQ or executables."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
repo = Path("/home/mouse9911/gits/leo-tracker-arm-presence")
destination = repo / "reports/evidence/2026_09_08_scanner_glrt_userspace_bundle"
destination.mkdir(parents=True, exist_ok=False)
selected = ["build_bundle.py", "exercise_bundle.py", "archive_bundle.py", "receipt.json",
            "configure.json", "compile.json", "local-stage-receipt.json", "ppu-tests.xml",
            "leo-tests.xml", "release/bundle.json", "release/algorithm.json",
            "release/configuration.json", "release/worker.build.json",
            "release/libleo-scanner-glrt.so.build.json"]
for name in ("iiod", "worker", "libleo-scanner-glrt.so", "libfftw3.so.3", "libiio.so.0",
             "libxml2.so.2", "libz.so.1"):
    selected.extend([f"header-{name}.json", f"dynamic-{name}.json"])
index = {}
for name in selected:
    source, target = root / name, destination / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    index[name] = dict(bytes=source.stat().st_size, sha256=digest)
tests = {}
for component in ("ppu", "leo"):
    suites = ET.parse(root / f"{component}-tests.xml").getroot().findall("testsuite")
    tests[component] = {key: sum(int(suite.attrib[key]) for suite in suites)
                        for key in ("tests", "failures", "errors", "skipped")}
revisions = {}
for name, path in (("leo", repo), ("ppu", repo.parent / "pluto-plus-utils-arm-glrt-host"),
                   ("libiio", repo.parent / "libiio-arm-glrt-frame-integration")):
    revisions[name] = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"],
                                              text=True).strip()
record = dict(schema="org.leo.research.scanner-glrt-userspace-bundle-evidence/v1",
              artifacts=index, tests=tests, revisions=revisions,
              local_release=str(root / "release"), radio_operations=0,
              scope="Portable lifecycle tests, local shell staging and ARM cross-build only")
with (destination / "index.json").open("x") as stream:
    json.dump(record, stream, indent=2)
    stream.write("\n")
print(json.dumps(dict(artifacts=len(index), bytes=sum(item["bytes"] for item in index.values()),
                     tests=tests, revisions=revisions), indent=2))
